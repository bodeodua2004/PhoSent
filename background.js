// Đặt địa chỉ API của bạn cho phân tích bài báo đơn lẻ
const ANALYZE_ARTICLE_API_URL = 'http://127.0.0.1:8000/analyze_single_article';

console.log("Background service worker đã được khởi động.");

// Lắng nghe các tin nhắn từ các content scripts hoặc popup scripts
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    // Để xử lý bất đồng bộ, luôn trả về `true` từ listener
    // và gọi `sendResponse` khi Promise được giải quyết.

    // --- Xử lý yêu cầu lấy nội dung bài báo từ content script (gửi từ popup) ---
    if (request.action === "getArticleContent") {
        console.log("Background: Nhận yêu cầu 'getArticleContent' từ popup.");
        (async () => { // Bọc logic bất đồng bộ trong IIFE
            try {
                const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
                if (!tab || !tab.id) {
                    sendResponse({ success: false, error: "Không tìm thấy tab đang hoạt động." });
                    return;
                }
                const contentResponse = await chrome.tabs.sendMessage(tab.id, { action: "getArticleContent" });
                sendResponse(contentResponse); // Chuyển tiếp phản hồi từ content script về popup
            } catch (error) {
                console.error("Background: Lỗi khi yêu cầu nội dung từ content script:", error);
                sendResponse({ success: false, error: error.message });
            }
        })();
        return true; // Quan trọng: Cho biết sendResponse sẽ được gọi bất đồng bộ
    }

    // --- Xử lý yêu cầu phân tích bài báo (gửi từ popup) ---
    if (request.action === "analyzeArticle") {
        console.log("Background: Nhận yêu cầu 'analyzeArticle' từ popup.");
        const { title, content, article_id } = request.payload;

        (async () => { // Bọc logic bất đồng bộ trong IIFE
            try {
                const response = await fetch(ANALYZE_ARTICLE_API_URL, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        title: title,
                        content: content,
                        article_id: article_id
                    })
                });

                if (!response.ok) {
                    const errorText = await response.text();
                    throw new Error(`Lỗi HTTP từ API: ${response.status} - ${errorText}`);
                }

                const data = await response.json();
                console.log("Background: Nhận dữ liệu phân tích từ API:", data);

                sendResponse({ success: true, data: data });

            } catch (error) {
                console.error("Background: Lỗi khi gọi API backend:", error);
                sendResponse({ success: false, error: error.message });
            }
        })(); // Gọi IIFE ngay lập tức
        return true; // Quan trọng: Cho biết sendResponse sẽ được gọi bất đồng bộ
    }
});
