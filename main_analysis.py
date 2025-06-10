import os
import json
import pandas as pd
import re
import time
import unicodedata
import requests
from bs4 import BeautifulSoup as bs
from openai import OpenAI
from pydantic import BaseModel
from dotenv import load_dotenv

# Import FastAPI và Uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Union

# Import ClassificationModel (giữ nguyên từ simpletransformers)
from simpletransformers.classification import ClassificationModel

# --- 0. CẤU HÌNH BAN ĐẦU VÀ TẢI TỪ ĐIỂN ---
load_dotenv()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.87 Safari/537.36',
}
requests.packages.urllib3.disable_warnings()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def read_file(path):
    """Đọc nội dung file văn bản."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# Đảm bảo các file dictionary_companies.csv và dictionary_sectors.csv có trong cùng thư mục
company_dictionary = read_file("dictionary_companies.csv")
sector_dictionary = read_file("dictionary_sectors.csv")

# --- 1. ĐỊNH NGHĨA CÁC MODEL Pydantic CHO ĐẦU RA TỪ OPENAI ---
class Company(BaseModel):
    company_name: str
    company_stock_id: str

class Sector(BaseModel):
    id: str
    article: str
    sector: str
    companies: list[Company]

# Các lớp kết quả tùy chỉnh (có thể bỏ qua nếu chỉ dùng Pydantic models)
class CompanyResult:
    def __init__(self, name, stockId):
        self.company_name = name
        self.company_stock_id = stockId

class SectorResult:
    def __init__(self, id, article, sector, companies):
        self.id = id
        self.article = article
        self.sector = sector
        self.companies = companies

def convert_company(c: Company) -> CompanyResult:
    return CompanyResult(name=c.company_name, stockId=c.company_stock_id)

def convert_sector(s: Sector) -> SectorResult:
    company_results = [convert_company(c) for c in s.companies]
    return SectorResult(
        id=s.id,
        article=s.id,
        sector=s.sector,
        companies=company_results
    )

def sector_result_to_dict(sr: SectorResult):
    return {
        "id": sr.id,
        "article": sr.article,
        "sector": sr.sector,
        "companies": [
            {
                "company_name": c.company_name,
                "company_stock_id": c.company_stock_id
            }
            for c in sr.companies
        ]
    }

# --- 2. ĐỊNH NGHĨA MODEL Pydantic CHO ĐẦU VÀO CỦA API MỚI ---
class ArticleAnalysisRequest(BaseModel):
    title: str
    content: str
    article_id: str # Thêm ID để dễ theo dõi

# --- 3. ĐỊNH NGHĨA MODEL Pydantic CHO ĐẦU RA CỦA API MỚI ---
class SingleArticleAnalysisResponse(BaseModel):
    sentiment_text_label: str
    sector: str
    companies: List[Company] # Trả về list các Pydantic Company model

# --- 4. TẢI MÔ HÌNH PHÂN TÍCH CẢM XÚC ĐÃ HUẤN LUYỆN ---
NUM_LABELS_SENTIMENT_MODEL = 3

# --- KHỞI TẠO APP FASTAPI ---
app = FastAPI()

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Cho phép tất cả các nguồn (domain) truy cập
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Biến toàn cục để lưu DataFrame kết quả sau khi xử lý.
# Khởi tạo mặc định để tránh lỗi khi bỏ qua phân tích ban đầu
final_output_df_global = pd.DataFrame(columns=['id', 'date', 'title', 'link', 'content', 'sector', 'companies',
                                               'sentiment_label_predicted', 'sentiment_text_label',
                                               'sentiment_score', 'He_so', 'article_score'])
total_market_score_global = 0.0
market_evaluation_global = "Trung lập" # Giá trị mặc định

sentiment_model_global = None # Lưu mô hình sentiment vào biến global

# --- HÀM HỖ TRỢ: Thực hiện toàn bộ quy trình phân tích dữ liệu ---
async def _perform_full_analysis():
    global final_output_df_global, total_market_score_global, market_evaluation_global

    print("\n--- BẮT ĐẦU QUY TRÌNH PHÂN TÍCH DỮ LIỆU ĐẦU VÀO ---")

    # Đọc dữ liệu từ file CSV đã crawl
    economy_articles_path = "economy_articles.csv"
    try:
        df_articles = pd.read_csv(economy_articles_path, encoding='utf-8')
        print(f"Đã đọc thành công {len(df_articles)} bài báo từ '{economy_articles_path}'")
    except FileNotFoundError:
        print(f"LỖI: Không tìm thấy file '{economy_articles_path}'. Vui lòng chạy data_extraction.py.")
        return None, None, None # Trả về None nếu có lỗi
    except Exception as e:
        print(f"LỖI khi đọc file '{economy_articles_path}': {e}")
        return None, None, None

    # Xử lý từng bài báo
    final_results = []
    # Giới hạn số lượng bài báo để tránh tốn quá nhiều thời gian/chi phí API khi khởi động/làm mới
    # Bạn có thể điều chỉnh hoặc loại bỏ giới hạn này trong môi trường production
    for index, row in df_articles.iterrows():
        if index >= 18:
            break

        article_id = row['id']
        title = row['title']
        content_text = row['content']

        # Đảm bảo content_text là chuỗi
        if not isinstance(content_text, str):
            content_text = ""
            print(f"DEBUG: Bài báo ID {article_id} có nội dung rỗng/không phải chuỗi. Gán rỗng.")

        article_for_openai = f"id,title,content\n{article_id},{title},{content_text}"

        extracted_sector = "Unknown"
        extracted_companies: List[Company] = []
        try:
            openai_response = client.responses.parse(
                model="gpt-4o",
                input=[
                    {
                        "role": "system",
                        "content": f"""Bạn là một chuyên gia trích xuất dữ liệu có cấu trúc.
                        # Nhiệm vụ
                        Phân tích bài báo dựa trên 2 dictionary đã cho (ở dạng CSV). Đầu ra là một danh sách các object theo schema đã cung cấp.
                        # Input Format
                        Là 1 file csv với các cột: id, title, content, tương ứng với id, tiêu đề và nội dung bài báo
                        # Mô tả
                        - Chỉ ra ngành được nhắc đến chủ yếu trong danh sách các ngành được cung cấp trong Dictionary 2.
                        - Tìm các công ty thuộc ngành đó được nhắc đến ở trong bài báo, đồng thời có trong dictionary 1.
                        - Một ngành có thể chứa nhiều công ty.
                        # Output Format
                        Là 1 json object, có dạng
                        {{
                        id: tương ứng với id của input
                        article: tên bài báo,
                        sector: tên ngành,
                        companies: [
                            {{
                                company_name: tên công ty,
                                company_stock_id: mã cổ phiếu
                            }}
                        ]
                        }}"""
                    },
                    {
                        "role": "user",
                        "content": f"""# Dictionary 1 (STT,Mã cp,Tên chính thức,Ngành,Từ khóa)
                        {company_dictionary}
                        # Dictionary 2 (STT,Ngành)
                        {sector_dictionary}
                        # Bài báo
                        {article_for_openai}
                        """
                    }
                ],
                text_format=Sector,
            )
            extracted_sector = openai_response.output_parsed.sector
            extracted_companies = openai_response.output_parsed.companies
        except Exception as e:
            print(f"❌ Lỗi khi gọi OpenAI: {e}")
            extracted_sector = "Unknown"
            extracted_companies = []

        predicted_sentiment_label = -99
        sentiment_text_label = "Lỗi"
        try:
            sentiment_predictions, _ = sentiment_model_global.predict([content_text])
            predicted_sentiment_label = sentiment_predictions[0]
            sentiment_text_label_map = {0: "Tích cực", 1: "Tiêu cực", 2: "Trung lập"}
            sentiment_text_label = sentiment_text_label_map.get(predicted_sentiment_label, "Không xác định")
        except Exception as e:
            print(f"❌ Lỗi khi phân tích sentiment: {e}")

        final_results.append({
            "id": article_id, "date": row['date'], "title": title, "link": row['link'],
            "content": content_text, "sector": extracted_sector, "companies": extracted_companies,
            "sentiment_label_predicted": predicted_sentiment_label, "sentiment_text_label": sentiment_text_label
        })
        time.sleep(0.5)

    df_result = pd.DataFrame(final_results)

    # Xử lý cột 'companies' cho DataFrame để tránh lỗi JSON dump khi lưu CSV/chuyển đổi
    # Chuyển đổi list of Pydantic models sang chuỗi JSON
    df_result['companies'] = df_result['companies'].apply(lambda x: json.dumps([c.model_dump() for c in x], ensure_ascii=False) if x else "[]")


    # Đọc file hệ số ngành
    sector_coefficients_path = 'sector_coefficients.csv'
    try:
        df_sector_coeffs = pd.read_csv(sector_coefficients_path, encoding='utf-8')
    except Exception as e:
        print(f"LỖI khi đọc file hệ số ngành: {e}. Vui lòng kiểm tra encoding và tên cột.")
        df_sector_coeffs = pd.DataFrame(columns=['sector', 'He_so'])

    # Ánh xạ điểm cảm xúc
    sentiment_score_map = {
        "Tích cực": 1, "Trung lập": 0, "Tiêu cực": -1, "Lỗi": 0, "Không xác định": 0
    }
    df_result['sentiment_score'] = df_result['sentiment_text_label'].map(sentiment_score_map).fillna(0)

    # Kết hợp hệ số ngành
    df_result = pd.merge(df_result, df_sector_coeffs, left_on='sector', right_on='sector', how='left')
    df_result['He_so'] = df_result['He_so'].fillna(1)

    # Tính điểm bài báo và tổng điểm
    df_result['article_score'] = df_result['sentiment_score'] * df_result['He_so'].fillna(0)
    df_result['article_score'] = df_result['article_score'].fillna(0)

    total_market_score = df_result['article_score'].sum()
    if total_market_score < -20: market_evaluation = "Tiêu cực"
    elif -20 <= total_market_score <= 20: market_evaluation = "Trung lập"
    else: market_evaluation = "Tích cực"
    
    print("--- KẾT THÚC QUY TRÌNH PHÂN TÍCH DỮ LIỆU ĐẦU VÀO ---")
    return df_result, total_market_score, market_evaluation


# --- HÀM TẢI MÔ HÌNH VÀ DỮ LIỆU BAN ĐẦU KHI KHỞI ĐỘNG SERVER ---
@app.on_event("startup")
async def load_initial_data():
    global sentiment_model_global, final_output_df_global, total_market_score_global, market_evaluation_global

    print("\n--- APP STARTUP: Đang tải mô hình và xử lý dữ liệu lần đầu ---")
    try:
        sentiment_model_global = ClassificationModel(
            "auto",
            "outputs/",
            use_cuda=False,
            num_labels=NUM_LABELS_SENTIMENT_MODEL,
            args={"tokenizer_type": "auto", "silent": True}
        )
        print("Mô hình phân tích cảm xúc đã được tải thành công!")
    except Exception as e:
        print(f"LỖI NGHIÊM TRỌNG: Không thể tải mô hình phân tích cảm xúc khi khởi động. Lỗi: {e}")
        raise HTTPException(status_code=500, detail=f"Không thể tải mô hình phân tích cảm xúc: {e}")

    # --- KIỂM TRA BIẾN MÔI TRƯỜNG ĐỂ BỎ QUA PHÂN TÍCH BAN ĐẦU ---
    skip_initial_analysis = os.getenv("SKIP_INITIAL_ANALYSIS", "False").lower() == "true"
    
    if skip_initial_analysis:
        print("\n--- APP STARTUP: Bỏ qua phân tích dữ liệu ban đầu theo cấu hình SKIP_INITIAL_ANALYSIS=True ---")
        # Giữ các giá trị mặc định cho market data
        # final_output_df_global đã được khởi tạo là DataFrame rỗng
        # total_market_score_global đã được khởi tạo là 0.0
        # market_evaluation_global đã được khởi tạo là "Trung lập"
    else:
        # Nếu không bỏ qua, thực hiện phân tích đầy đủ
        final_output_df_global, total_market_score_global, market_evaluation_global = await _perform_full_analysis()
        if final_output_df_global is None:
            print("Cảnh báo: Dữ liệu ban đầu không được tải đầy đủ khi khởi động.")
        else:
            print("--- APP STARTUP: Xử lý dữ liệu ban đầu hoàn tất! ---")


# --- ĐỊNH NGHĨA CÁC API ENDPOINTS ---

@app.get("/")
async def read_root():
    """Endpoint gốc để kiểm tra API."""
    return {"message": "API phân tích thị trường đang chạy!"}

@app.get("/market_data")
async def get_market_data():
    """Endpoint trả về tất cả dữ liệu phân tích bài báo và điểm số."""
    if final_output_df_global.empty and total_market_score_global == 0.0 and market_evaluation_global == "Trung lập":
        # Nếu bỏ qua phân tích ban đầu, trả về thông báo hợp lý hoặc giá trị mặc định
        return JSONResponse(content={
            "articles_data": [],
            "total_market_score": 0.0,
            "market_evaluation": "Chưa phân tích" # Thay đổi để rõ ràng hơn
        })
    
    df_json = final_output_df_global.to_dict(orient='records')
    
    return JSONResponse(content={
        "articles_data": df_json,
        "total_market_score": total_market_score_global,
        "market_evaluation": market_evaluation_global
    })

@app.post("/analyze_single_article", response_model=SingleArticleAnalysisResponse)
async def analyze_single_article(request_data: ArticleAnalysisRequest):
    """
    Endpoint để phân tích một bài báo cụ thể từ frontend.
    """
    global sentiment_model_global, company_dictionary, sector_dictionary, client

    if sentiment_model_global is None:
        raise HTTPException(status_code=503, detail="Mô hình sentiment chưa được tải hoặc có lỗi khi khởi động.")

    title = request_data.title
    content_text = request_data.content
    article_id = request_data.article_id

    print(f"\n========== API REQUEST: Đang phân tích bài báo ID: {article_id} - Tiêu đề: {title[:50]}... ==========")

    extracted_sector = "Unknown"
    extracted_companies: List[Company] = [] 

    article_for_openai = f"id,title,content\n{article_id},{title},{content_text}"
    try:
        openai_response = client.responses.parse(
            model="gpt-4o",
            input=[
                {
                    "role": "system",
                    "content": f"""Bạn là một chuyên gia trích xuất dữ liệu có cấu trúc.
                    # Nhiệm vụ
                    Phân tích bài báo dựa trên 2 dictionary đã cho (ở dạng CSV). Đầu ra là một danh sách các object theo schema đã cung cấp.
                    # Input Format
                    Là 1 file csv với các cột: id, title, content, tương ứng với id, tiêu đề và nội dung bài báo
                    # Mô tả
                    - Chỉ ra ngành được nhắc đến chủ yếu trong danh sách các ngành được cung cấp trong Dictionary 2.
                    - Tìm các công ty thuộc ngành đó được nhắc đến ở trong bài báo, đồng thời có trong dictionary 1.
                    - Một ngành có thể chứa nhiều công ty.
                    # Output Format
                    Là 1 json object, có dạng
                    {{
                    id: tương ứng với id của input
                    article: tên bài báo,
                    sector: tên ngành,
                    companies: [
                        {{
                            company_name: tên công ty,
                            company_stock_id: mã cổ phiếu
                        }}
                    ]
                    }}"""
                },
                {
                    "role": "user",
                    "content": f"""# Dictionary 1 (STT,Mã cp,Tên chính thức,Ngành,Từ khóa)
                    {company_dictionary}
                    # Dictionary 2 (STT,Ngành)
                    {sector_dictionary}
                    # Bài báo
                    {article_for_openai}
                    """
                }
            ],
            text_format=Sector,
        )
        extracted_sector = openai_response.output_parsed.sector
        extracted_companies = openai_response.output_parsed.companies
        print(f"✅ API Request: OpenAI phân tích xong ngành/công ty. Ngành: {extracted_sector}")
    except Exception as e:
        print(f"❌ API Request: Lỗi khi gọi OpenAI cho bài báo ID {article_id}: {e}")
        extracted_sector = "Unknown"
        extracted_companies = []

    sentiment_text_label = "Lỗi"
    try:
        if not isinstance(content_text, str):
            content_text = ""
            print(f"DEBUG: Bài báo ID {article_id} có nội dung rỗng/không phải chuỗi. Gán rỗng để phân tích.")

        sentiment_predictions, _ = sentiment_model_global.predict([content_text])
        predicted_sentiment_label = sentiment_predictions[0]
        sentiment_text_label_map = {0: "Tích cực", 1: "Tiêu cực", 2: "Trung lập"}
        sentiment_text_label = sentiment_text_label_map.get(predicted_sentiment_label, "Không xác định")
        print(f"✅ API Request: Sentiment dự đoán: Nhãn số: {predicted_sentiment_label} -> Nhãn văn bản: {sentiment_text_label}")
    except Exception as e:
        print(f"❌ API Request: Lỗi khi phân tích sentiment cho bài báo ID {article_id}: {e}")

    return SingleArticleAnalysisResponse(
        sentiment_text_label=sentiment_text_label,
        sector=extracted_sector,
        companies=extracted_companies
    )

@app.get("/refresh_market_data")
async def refresh_market_data():
    """
    Endpoint để làm mới dữ liệu tổng quan thị trường từ file CSV mới nhất.
    Nên gọi sau khi data_extraction.py chạy xong.
    """
    global final_output_df_global, total_market_score_global, market_evaluation_global
    print("\n--- API REFRESH: Đang làm mới dữ liệu tổng quan thị trường ---")
    
    new_df, new_total_score, new_market_eval = await _perform_full_analysis()

    if new_df is None:
        raise HTTPException(status_code=500, detail="Không thể làm mới dữ liệu. Vui lòng kiểm tra log server.")
    
    final_output_df_global = new_df
    total_market_score_global = new_total_score
    market_evaluation_global = new_market_eval
    
    print("--- API REFRESH: Dữ liệu tổng quan thị trường đã được làm mới thành công! ---")
    return {"message": "Dữ liệu tổng quan thị trường đã được làm mới.", "total_score": new_total_score, "evaluation": new_market_eval}
