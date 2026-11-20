/* 1. Ảnh được chọn và trạng thái tính sức chứa. */
const imageInput = document.getElementById("image");
const preview = document.getElementById("preview");
const dropzone = document.getElementById("dropzone");
let previewUrl;
let availableCapacity = null;
let capacityTimer;
let capacityRequest = 0;
let jpegSource = selected("method") === "jpeg_dct";
let imageChoice = 0;

function selected(name) {
    const input = document.querySelector('input[name="' + name + '"]:checked');
    return input ? input.value : "";
}

async function showImage() {
    const choice = ++imageChoice;
    const file = imageInput.files[0];
    availableCapacity = null;
    capacityRequest += 1;
    imageInput.setCustomValidity("");
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    if (!file) {
        preview.hidden = true;
        dropzone.classList.remove("has-image");
        document.getElementById("file-info").hidden = true;
        updateCapacity();
        return;
    }
    // Đọc chữ ký tệp, không đoán định dạng chỉ từ đuôi tên.
    const signature = new Uint8Array(await file.slice(0, 3).arrayBuffer());
    if (choice !== imageChoice) return;
    updateFormat(signature[0] === 255 && signature[1] === 216);
    document.getElementById("file-info").hidden = false;
    document.getElementById("file-name").textContent = file.name;
    document.getElementById("file-detail").textContent = (file.size / 1024).toFixed(1) + " KB · Đã chọn tệp";
    preview.onload = function () {
        preview.hidden = false;
        dropzone.classList.add("has-image");
        document.getElementById("file-detail").textContent = preview.naturalWidth + " × " + preview.naturalHeight + " px · " + (file.size / 1024).toFixed(1) + " KB";
        if (preview.naturalWidth * preview.naturalHeight > 4000000) {
            imageInput.setCustomValidity("Ảnh tối đa 4 triệu pixel.");
        }
        queueCapacity();
    };
    preview.onerror = function () {
        preview.hidden = true;
        dropzone.classList.remove("has-image");
        imageInput.setCustomValidity("Không đọc được ảnh đã chọn.");
    };
    previewUrl = URL.createObjectURL(file);
    preview.src = previewUrl;
    updateCapacity();
}
if (imageInput) imageInput.addEventListener("change", showImage);

/* 2. Kéo thả một ảnh. */
if (dropzone) {
    dropzone.addEventListener("dragover", function (event) {
        event.preventDefault();
        dropzone.classList.add("dragover");
    });
    dropzone.addEventListener("dragleave", function () {
        dropzone.classList.remove("dragover");
    });
    dropzone.addEventListener("drop", function (event) {
        event.preventDefault();
        dropzone.classList.remove("dragover");
        const file = event.dataTransfer.files[0];
        if (!file) return;
        const files = new DataTransfer();
        files.items.add(file);
        imageInput.files = files.files;
        showImage();
    });
}

/* JPEG phải dùng hệ số DCT; PNG/BMP dùng thuật toán pixel. */
function updateFormat(isJPEG) {
    jpegSource = isJPEG;
    const radios = document.querySelectorAll('input[name="method"]');
    if (!radios.length) return;
    radios.forEach(function (radio) {
        radio.disabled = isJPEG ? radio.value !== "jpeg_dct" : radio.value === "jpeg_dct";
    });
    if (isJPEG) {
        document.querySelector('input[name="method"][value="jpeg_dct"]').checked = true;
    } else if (selected("method") === "jpeg_dct") {
        document.querySelector('input[name="method"][value="replacement"]').checked = true;
    }
    const note = document.getElementById("output-format");
    if (note) note.textContent = isJPEG ? "JPEG đầu vào → JPEG đầu ra · nhúng DCT, không nén pixel lại sau nhúng" : "PNG → PNG · BMP → BMP";
    updateMethod();
    updatePosition();
}

/* 3. Thuật toán và số LSB. */
function updateMethod() {
    const method = selected("method");
    if (!method) return;
    const replacement = method === "replacement";
    document.getElementById("bit-settings").hidden = !replacement;
    document.querySelectorAll('input[name="k"]').forEach(function (input) {
        input.disabled = !replacement;
    });
    const note = document.getElementById("method-note");
    if (replacement) note.textContent = "Thay trực tiếp 1/2/3 bit cuối mỗi giá trị màu.";
    if (method === "matching") note.textContent = "1 bit mỗi giá trị màu; điều chỉnh ±1 nếu LSB chưa khớp.";
    if (method === "lsbmr") note.textContent = "2 bit/cặp RGB. Tại biên 0/255 hoặc nhóm màu, có thể sửa cả hai giá trị đi 1.";
    if (method === "jpeg_dct") note.textContent = "JPEG DCT: 1 bit/hệ số AC có |v| ≥ 2 của thành phần đầu. Không dùng LSB pixel. JPEG progressive có thể chuẩn hóa baseline trước khi nhúng.";
    queueCapacity();
}

/* 4. Vị trí: chỉ yêu cầu khóa/ngưỡng khi chế độ cần chúng. */
function updatePosition() {
    const mode = selected("position_mode");
    if (!mode) return;
    const keyed = mode === "keyed";
    const spatial = mode === "adaptive" || mode === "edge";
    document.getElementById("key-settings").hidden = !keyed;
    document.getElementById("key").disabled = !keyed;
    document.getElementById("key").required = keyed;
    document.getElementById("threshold-settings").hidden = !spatial;
    document.getElementById("threshold").disabled = !spatial;
    document.getElementById("threshold").required = spatial;
    const note = document.getElementById("position-note");
    if (mode === "sequential") note.textContent = "Tuần tự từ góc trên trái; lần lượt R, G, B; bỏ alpha.";
    if (keyed) note.textContent = "Cùng khóa tạo lại cùng thứ tự vị trí. Phân biệt hoa/thường và khoảng trắng; khóa không mã hóa nội dung.";
    if (mode === "adaptive") note.textContent = "Ưu tiên khối 8×8 có độ tương phản cao. Khi trích xuất phải chọn cùng ngưỡng. Giữ 5 bit cao để vị trí ổn định.";
    if (mode === "edge") note.textContent = "Chọn pixel có độ chênh với bên trái/bên trên vượt ngưỡng, ưu tiên biên mạnh. Cần cùng ngưỡng khi trích xuất.";
    if (selected("method") === "jpeg_dct") {
        if (mode === "sequential") note.textContent = "Tuần tự theo các hệ số AC đủ điều kiện trong JPEG.";
        if (mode === "adaptive") note.textContent = "Ưu tiên block có tổng floor(|AC|/2) đạt ngưỡng. Điểm giữ ổn định sau nhúng.";
        if (mode === "edge") note.textContent = "Ưu tiên block có chênh lệch hệ số DC với block trái/trên đạt ngưỡng. DC không bị sửa.";
    }
    queueCapacity();
}

/* 5. Nhờ Python tính sức chứa thật, kể cả vùng thích nghi/biên. */
function queueCapacity() {
    if (!document.getElementById("capacity")) return;
    availableCapacity = null;
    capacityRequest += 1;
    clearTimeout(capacityTimer);
    updateCapacity();
    if (imageInput.files.length) capacityTimer = setTimeout(requestCapacity, 220);
}

async function requestCapacity() {
    const token = ++capacityRequest;
    const output = document.getElementById("capacity");
    const file = imageInput.files[0];
    if (!file) return;
    output.textContent = "Đang tính sức chứa của vùng được chọn…";
    const data = new FormData();
    data.append("image", file);
    data.append("method", selected("method"));
    data.append("k", selected("method") === "replacement" ? selected("k") : "1");
    data.append("position_mode", selected("position_mode"));
    data.append("key", document.getElementById("key").disabled ? "" : document.getElementById("key").value);
    data.append("threshold", document.getElementById("threshold").disabled ? "12" : document.getElementById("threshold").value);
    try {
        const response = await fetch("/capacity", {method:"POST", body:data});
        if (!response.ok) {
            const html = new DOMParser().parseFromString(await response.text(), "text/html");
            const detail = html.querySelector(".error-panel p");
            throw new Error(detail ? detail.textContent : "Không tính được sức chứa. Kiểm tra ảnh và các tùy chọn.");
        }
        const result = await response.json();
        if (token !== capacityRequest) return;
        availableCapacity = result.capacity_bytes;
        updateCapacity();
    } catch (error) {
        if (token !== capacityRequest) return;
        output.textContent = error.message;
    }
}

function updateCapacity() {
    const output = document.getElementById("capacity");
    if (!output) return;
    const bar = document.getElementById("capacity-bar");
    if (availableCapacity === null) {
        output.textContent = imageInput.files.length ? "Chờ tính sức chứa theo cấu hình…" : "Chọn ảnh để tính sức chứa.";
        bar.style.width = "0%";
        return;
    }
    let used = new TextEncoder().encode(document.getElementById("message").value).length;
    const file = document.getElementById("payload").files[0];
    if (file) used = file.size;
    const percent = availableCapacity ? Math.round(used / availableCapacity * 100) : 0;
    output.textContent = "Nội dung: " + used.toLocaleString("vi-VN") + " / " + availableCapacity.toLocaleString("vi-VN") + " byte (" + percent + "%)";
    bar.style.width = Math.min(100, percent) + "%";
    bar.classList.toggle("over", used > availableCapacity);
    document.getElementById("capacity-help").textContent = used > availableCapacity ? "Vượt sức chứa: chọn ảnh lớn hơn, giảm nội dung hoặc giảm ngưỡng vùng." : "Đã trừ header 12 byte; tính theo số vị trí thật được chọn.";
}

/* 6. Gắn các hàm vào giao diện. */
document.querySelectorAll('input[name="method"]').forEach(function (input) {
    input.addEventListener("change", updateMethod);
});
document.querySelectorAll('input[name="position_mode"]').forEach(function (input) {
    input.addEventListener("change", updatePosition);
});
document.querySelectorAll('input[name="k"]').forEach(function (input) {
    input.addEventListener("change", queueCapacity);
});
for (const id of ["key", "threshold"]) {
    const input = document.getElementById(id);
    if (input) input.addEventListener("input", queueCapacity);
}
const messageInput = document.getElementById("message");
if (messageInput) messageInput.addEventListener("input", updateCapacity);
const payloadInput = document.getElementById("payload");
if (payloadInput) payloadInput.addEventListener("change", updateCapacity);
updateFormat(jpegSource);

/* 7. Sao chép nội dung đã trích xuất. */
const copyButton = document.getElementById("copy-button");
if (copyButton) {
    copyButton.addEventListener("click", async function () {
        try {
            await navigator.clipboard.writeText(document.getElementById("message-result").textContent);
            copyButton.textContent = "Đã sao chép";
        } catch (error) {
            copyButton.textContent = "Hãy chọn nội dung để sao chép";
        }
    });
}
