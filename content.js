// content.js không tự động phân tích hay hiển thị nữa.
// Nó chỉ lắng nghe yêu cầu từ background script.

console.log("Content script for Vneconomy: Sẵn sàng nhận yêu cầu từ background.");

// Lắng nghe các tin nhắn từ background script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "getArticleContent") {
        console.log("Content script: Nhận yêu cầu lấy nội dung bài báo.");

        // --- 1. TRÍCH XUẤT TIÊU ĐỀ VÀ NỘI DUNG BÀI BÁO ---
        const articleTitleElement = document.querySelector('h1.detail__title'); 
        const articleContentElements = document.querySelectorAll('div.detail__content p'); 

        let articleTitle = articleTitleElement ? articleTitleElement.textContent.trim() : '';
        let articleContent = '';
        
        if (!articleTitleElement) {
            console.warn("Content script: Không tìm thấy phần tử tiêu đề (h1.detail__title).");
            articleTitle = 'Không tìm thấy tiêu đề';
        } else {
            console.log("Content script: Đã tìm thấy tiêu đề:", articleTitle);
        }

        if (articleContentElements.length > 0) {
            articleContentElements.forEach(p => {
                articleContent += p.textContent.trim() + '\n';
            });
            console.log("Content script: Đã tìm thấy nội dung bài báo (số đoạn p):", articleContentElements.length);
        } else {
            articleContent = ''; 
            console.warn("Content script: Không tìm thấy phần tử nội dung (div.detail__content p).");
        }

        // --- 2. GỬI NỘI DUNG TRỞ LẠI CHO BACKGROUND SCRIPT ---
        console.log("Content script: Gửi nội dung bài báo về cho background script.");
        sendResponse({ 
            success: true, 
            payload: {
                title: articleTitle,
                content: articleContent,
                article_id: `article_${Date.now()}` // ID tạm thời
            }
        });
        return true; // Quan trọng: Để sendResponse hoạt động bất đồng bộ
    }
});

// Hàm displayAnalysisResults không còn được sử dụng trong content script
// vì kết quả sẽ hiển thị trong popup. Có thể xóa hoặc giữ lại nếu có ý định dùng lại.
// function displayAnalysisResults(...) { ... }
