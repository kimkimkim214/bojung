import os
import sys
import io

from dotenv import load_dotenv
load_dotenv()  # .env 파일 자동 로드

from google import genai
from PIL import Image
import gradio as gr

# API 키 검증
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("[ERROR] GEMINI_API_KEY가 설정되지 않았습니다.")
    print("  .env 파일을 생성하고 GEMINI_API_KEY=your_api_key_here 형식으로 입력하세요.")
    sys.exit(1)


def transfer_style_gemini(original_img, reference_img):
    """
    원본 이미지의 구조/형태를 유지하면서 참고 이미지의 채색 스타일을 적용합니다.

    Args:
        original_img: 구조를 유지할 원본 PIL Image
        reference_img: 스타일을 추출할 참고 PIL Image

    Returns:
        스타일이 적용된 PIL Image (원본과 동일한 크기)
    """
    if original_img is None or reference_img is None:
        gr.Warning("원본 이미지와 참고 이미지를 모두 업로드해주세요.")
        return None

    # 원본 크기 저장
    orig_width, orig_height = original_img.size

    # Gemini 클라이언트 초기화 (환경변수 GEMINI_API_KEY 자동 참조)
    client = genai.Client()

    prompt = (
        "첫 번째 원본 이미지의 구조, 형태, 피사체, 구도를 완벽하게 고정하고 유지해라. "
        "두 번째 참고 이미지에서는 채색 스타일, 색감, 조명, 붓터치 등 텍스처만 추출하여 "
        "첫 번째 원본 이미지에 덧입혀라. 원본의 형태 자체는 절대 변형하지 마라."
    )

    response = client.models.generate_content(
        model="gemini-2.0-flash-preview-image-generation",
        contents=[original_img, reference_img, prompt],
    )

    # 응답에서 이미지 파트 추출
    result_img = None
    for part in response.candidates[0].content.parts:
        if hasattr(part, "inline_data") and part.inline_data is not None:
            image_data = part.inline_data.data
            result_img = Image.open(io.BytesIO(image_data))
            break

    if result_img is None:
        raise ValueError("API 응답에서 이미지를 찾을 수 없습니다. 다시 시도해주세요.")

    # 원본 사이즈로 강제 리사이징
    result_img = result_img.resize((orig_width, orig_height), Image.Resampling.LANCZOS)

    return result_img


PASTE_JS = """
() => {
    let lastHoveredId = null;
    const TARGET_IDS = ['img_original', 'img_reference'];

    function setupHoverTracking() {
        TARGET_IDS.forEach(id => {
            const el = document.querySelector('#' + id);
            if (el) {
                el.addEventListener('mouseenter', () => { lastHoveredId = id; });
            }
        });
    }

    document.addEventListener('paste', e => {
        const imgItem = Array.from(e.clipboardData?.items ?? []).find(
            i => i.kind === 'file' && i.type.startsWith('image/')
        );
        if (!imgItem) return;

        const targetId = lastHoveredId ?? TARGET_IDS[0];
        const container = document.querySelector('#' + targetId);
        if (!container) return;

        const fileInput = container.querySelector('input[type="file"]');
        if (!fileInput) return;

        const file = imgItem.getAsFile();
        if (!file) return;

        e.preventDefault();
        const dt = new DataTransfer();
        dt.items.add(new File([file], 'paste.png', { type: file.type }));
        fileInput.files = dt.files;
        fileInput.dispatchEvent(new Event('change', { bubbles: true }));
    });

    // 컴포넌트가 DOM에 렌더링될 때까지 대기
    const timer = setInterval(() => {
        const ready = TARGET_IDS.every(id => document.querySelector('#' + id));
        if (ready) {
            setupHoverTracking();
            clearInterval(timer);
        }
    }, 300);
}
"""

# Gradio UI 구성
with gr.Blocks(title="Gemini 이미지 스타일 트랜스퍼", js=PASTE_JS) as demo:
    gr.Markdown("# Gemini 이미지 스타일 트랜스퍼")
    gr.Markdown("원본 이미지의 구조는 그대로 유지하면서 참고 이미지의 채색 스타일을 적용합니다.")

    with gr.Row():
        # 좌측 컬럼: 입력 영역
        with gr.Column():
            gr.Markdown("### 입력 영역")
            img_original = gr.Image(
                label="원본 이미지 (구조 고정용)",
                type="pil",
                sources=["upload", "clipboard"],
                elem_id="img_original",
            )
            img_reference = gr.Image(
                label="참고 이미지 (채색 스타일용)",
                type="pil",
                sources=["upload", "clipboard"],
                elem_id="img_reference",
            )
            btn_generate = gr.Button("스타일 융합하기", variant="primary")

        # 우측 컬럼: 출력 영역
        with gr.Column():
            gr.Markdown("### 출력 영역")
            img_result = gr.Image(
                label="최종 결과물 (원본 사이즈 동일)",
                type="pil",
                interactive=False,
            )

    # 이벤트 바인딩
    btn_generate.click(
        fn=transfer_style_gemini,
        inputs=[img_original, img_reference],
        outputs=img_result,
    )


if __name__ == "__main__":
    demo.launch()
