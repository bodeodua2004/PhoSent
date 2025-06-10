# PhoSent - Hướng dẫn sử dụng
## Set up backend

Tạo một API key trên OpenAI của bạn, đảm bảo là bạn có tiền trong tài khoản OpenAI

Tạo một file text đặt tên là .env, và paste API Key của bạn vào theo dạng: OPENAI_API_KEY=sk-OPENAI_KEY_CUA_BAN

Mở Terminal

Điều hướng đến thư mục Backend bằng lệnh cd DUONG_DAN_DEN_THU_MUC_CUA_BAN

Tạo một môi trường ảo với câu lệnh: python3 -m venv venv

Kích hoạt môi trường ảo với câu lệnh: source venv/bin/activate

Sau đó chạy câu lệnh: pip install -r requirements.txt --> để tải các thư viện cần thiết về

Chạy câu lệnh: python data_extraction.py --> chạy file thu thập dữ liệu các bài báo mới nhất

Sau khi chạy xong sẽ thu thập được file economy_articles.csv bao gồm dữ liệu từ các bài báo mới nhất

Sau đó chạy cây lệnh: uvicorn main_analysis:app --reload --> để khởi động backend, sẽ mất khoảng 4ph để khởi động hoàn toàn vì sẽ mất thời gian để chạy phân tích Market Sentiment

## Set up Frontend

Mở Google Chrome, truy cập đường dẫn: chrome://extensions/

Bật Developer mode ở trên góc trên bên phải

Chọn Load unpacked --> Chọn folder PhoSent để Select

Và thế là Extension của bạn đã sẵn sàng sử dụng

## Sử dụng Extension

Truy cập một bài báo trên Vneconomy

Bấm vào Extension PhoSent, chọn Phân tích bài báo đang đọc

Sau khoảng 10s, kết quả sẽ hiện lên bao gồm: Nhận định của bài báo; Ngành liên quan; Cổ phiếu liên quan

