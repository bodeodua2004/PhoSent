// Đặt địa chỉ API của bạn cho dữ liệu tổng quan thị trường
const MARKET_DATA_API_URL = 'http://127.0.0.1:8000/market_data';
// Đặt địa chỉ API của bạn cho phân tích bài báo đơn lẻ
const ANALYZE_ARTICLE_API_URL = 'http://127.0.0.1:8000/analyze_single_article';

/**
 * Lấy dữ liệu tổng quan thị trường từ API backend và cập nhật giao diện popup.
 */
async function fetchMarketData() {
    try {
        const response = await fetch(MARKET_DATA_API_URL);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        console.log('Dữ liệu tổng quan thị trường từ API:', data);

        const marketScoreElement = document.getElementById('market-score');
        const marketEvaluationElement = document.getElementById('market-evaluation');
        
        if (marketScoreElement) {
            marketScoreElement.textContent = data.total_market_score.toFixed(1);
        }
        if (marketEvaluationElement) {
            marketEvaluationElement.textContent = data.market_evaluation;
            marketEvaluationElement.className = `label sentiment-${data.market_evaluation.toLowerCase().replace(/\s/g, '_')}`;
        }
    } catch (error) {
        console.error('Lỗi khi lấy dữ liệu tổng quan thị trường từ API:', error);
        const container = document.querySelector('.container');
        if (container) {
            container.innerHTML = `
                <h1 class="title">PhoSent</h1>
                <div class="error-message" style="color: red; text-align: center; margin-top: 20px;">
                    Không thể tải dữ liệu tổng quan thị trường. <br> Vui lòng đảm bảo Backend API đang chạy tại ${MARKET_DATA_API_URL} <br>
                    Chi tiết lỗi: ${error.message}
                </div>
            `;
        }
    }
}

/**
 * Cập nhật giao diện hiển thị kết quả phân tích một bài báo cụ thể.
 * @param {object} results - Đối tượng chứa kết quả phân tích (sentiment_text_label, sector, companies).
 */
function updateSingleArticleResults(results) {
    const analysisContainer = document.getElementById('single-article-results');
    const analysisStatus = document.getElementById('analysis-status');
    const sentimentElement = document.getElementById('single-article-sentiment');
    const industryListElement = document.getElementById('single-article-industry-list');
    const stockListElement = document.getElementById('single-article-stock-list');

    if (analysisContainer) {
        analysisContainer.style.display = 'block'; // Hiển thị vùng kết quả
        analysisStatus.style.display = 'none'; // Ẩn trạng thái "Đang chờ phân tích..."
    }

    // Cập nhật cảm xúc
    if (sentimentElement) {
        sentimentElement.textContent = results.sentiment_text_label;
        sentimentElement.className = `news-sentiment-summary sentiment-${results.sentiment_text_label.toLowerCase().replace(/\s/g, '_')}`;
    }

    // Cập nhật ngành
    if (industryListElement) {
        const sectorName = results.sector || 'Không xác định';
        industryListElement.innerHTML = `<span>${sectorName}</span>`;
    }

    // Cập nhật mã cổ phiếu
    if (stockListElement) {
        // CHỈ HIỂN THỊ MÃ CỔ PHIẾU (c.company_stock_id)
        let companiesHtml = results.companies && results.companies.length > 0
            ? results.companies.map(c => `<span>${c.company_stock_id || 'N/A'}</span>`).join('') // Đã sửa ở đây
            : 'Không có mã cổ phiếu liên quan.';
        stockListElement.innerHTML = companiesHtml;
    }
}

/**
 * Xử lý lỗi khi phân tích bài báo đơn lẻ.
 * @param {string} message - Thông báo lỗi.
 */
function handleSingleArticleError(message) {
    const analysisContainer = document.getElementById('single-article-results');
    const analysisStatus = document.getElementById('analysis-status');

    if (analysisContainer) {
        analysisContainer.style.display = 'block';
    }
    if (analysisStatus) {
        analysisStatus.style.display = 'block';
        analysisStatus.style.color = 'red';
        analysisStatus.textContent = `Lỗi: ${message}`;
    }
    // Ẩn các phần kết quả khác nếu có lỗi
    const sentimentElement = document.getElementById('single-article-sentiment');
    const industryListElement = document.getElementById('single-article-industry-list');
    const stockListElement = document.getElementById('single-article-stock-list');
    
    if (sentimentElement) sentimentElement.textContent = '';
    if (industryListElement) industryListElement.innerHTML = '';
    if (stockListElement) stockListElement.innerHTML = '';
}


// --- Lắng nghe sự kiện click nút "Phân tích" ---
document.addEventListener('DOMContentLoaded', () => {
    fetchMarketData(); // Tải dữ liệu thị trường chung khi popup mở

    const analyzeButton = document.getElementById('analyze-button');
    if (analyzeButton) {
        analyzeButton.addEventListener('click', async () => {
            const analysisStatus = document.getElementById('analysis-status');
            const analysisContainer = document.getElementById('single-article-results');

            if (analysisStatus) {
                analysisStatus.style.display = 'block';
                analysisStatus.style.color = '#333';
                analysisStatus.textContent = 'Đang phân tích bài báo...';
            }
            if (analysisContainer) {
                analysisContainer.style.display = 'block'; // Hiển thị vùng chứa kết quả khi bắt đầu phân tích
                // Xóa nội dung cũ
                document.getElementById('single-article-sentiment').textContent = '';
                document.getElementById('single-article-industry-list').innerHTML = '';
                document.getElementById('single-article-stock-list').innerHTML = '';
            }

            try {
                // Bước 1: Lấy tab hiện tại
                let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
                
                if (!tab || !tab.url.startsWith('https://vneconomy.vn/')) {
                    handleSingleArticleError('Không phải trang bài báo Vneconomy.vn. Vui lòng mở bài báo để phân tích.');
                    return;
                }

                // Bước 2: Gửi tin nhắn đến content script trong tab hiện tại để lấy nội dung bài báo
                console.log("Popup: Yêu cầu content script lấy nội dung bài báo.");
                let contentResponse;
                try {
                    contentResponse = await chrome.tabs.sendMessage(tab.id, { action: "getArticleContent" });
                } catch (e) {
                    console.error("Popup: Lỗi khi gửi tin nhắn tới content script:", e);
                    handleSingleArticleError('Không thể kết nối với content script. Vui lòng thử tải lại trang hoặc tiện ích.');
                    return;
                }
                
                if (!contentResponse || !contentResponse.success || !contentResponse.payload) {
                    handleSingleArticleError('Không thể lấy nội dung bài báo từ trang. Đảm bảo content script đang chạy và trang đã tải hoàn tất.');
                    return;
                }

                const { title, content, article_id } = contentResponse.payload;

                if (!content.trim()) {
                    handleSingleArticleError('Nội dung bài báo rỗng. Không thể phân tích.');
                    return;
                }

                // Bước 3: Gửi nội dung bài báo đã lấy được đến background script để gọi API backend
                console.log("Popup: Gửi nội dung bài báo đến background script để phân tích.");
                let apiResponse;
                try {
                    apiResponse = await chrome.runtime.sendMessage({
                        action: "analyzeArticle",
                        payload: { title, content, article_id }
                    });
                    console.log("Popup: Giá trị apiResponse nhận được từ background:", apiResponse); // THÊM DÒNG LOG NÀY
                } catch (e) {
                    console.error("Popup: Lỗi khi gửi tin nhắn tới background script:", e);
                    handleSingleArticleError('Không thể kết nối với background script. Vui lòng thử tải lại tiện ích.');
                    return;
                }

                // Kiểm tra phản hồi từ background script
                if (apiResponse && apiResponse.success && apiResponse.data) {
                    console.log("Popup: Nhận kết quả phân tích từ background script:", apiResponse.data);
                    updateSingleArticleResults(apiResponse.data);
                } else {
                    // Cải thiện thông báo lỗi khi apiResponse không như mong đợi
                    // Đảm bảo truy cập thuộc tính một cách an toàn
                    const backendErrorMessage = (apiResponse && typeof apiResponse === 'object' && apiResponse.error) ? apiResponse.error : 'Không có phản hồi hợp lệ hoặc có lỗi không rõ từ background script.';
                    handleSingleArticleError(`Lỗi phân tích từ Backend: ${backendErrorMessage}`);
                }

            } catch (error) {
                console.error("Popup: Lỗi trong quá trình phân tích bài báo:", error);
                handleSingleArticleError(`Lỗi không xác định: ${error.message}.`);
            }
        });
    }
});
