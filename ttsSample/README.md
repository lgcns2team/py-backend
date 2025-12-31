# TTS RVC 프로젝트

텍스트를 음성으로 변환하고 RVC(Retrieval-based Voice Conversion)를 사용하여 특정 캐릭터의 목소리로 변조하는 프로젝트입니다.

## 🎯 기능

- **Edge-TTS**: 텍스트를 자연스러운 한국어 음성으로 변환
- **RVC 변환**: 학습된 모델을 사용하여 목소리를 특정 캐릭터의 목소리로 변조
- **피치 조절**: 음정을 조절하여 다양한 목소리 톤 생성

## 📋 요구사항

- **Python**: 3.10 권장 (3.8-3.10 지원, 3.11/3.13은 호환 문제 발생 가능)
- **pip**: 24.0 이하 버전 (pip<24.1)
- **RVC 모델 파일**: `.pth` 형식의 학습된 RVC 모델
- (선택) **인덱스 파일**: `.index` 형식의 인덱스 파일 (더 나은 품질을 위해 권장)

## 🚀 설치 방법

### 1. Python 3.10 설치 및 가상환경 생성

```bash
# pyenv를 사용하는 경우
pyenv install 3.10.15
pyenv local 3.10.15

# 가상환경 생성
python -m venv .venv

# 가상환경 활성화
source .venv/bin/activate  # macOS/Linux
# 또는
.venv\Scripts\activate  # Windows
```

### 2. pip 버전 다운그레이드

```bash
pip install "pip<24.1"
```

### 3. 의존성 패키지 설치

```bash
pip install -r requirements.txt
```

## 📝 사용 방법

### 1. RVC 모델 준비

프로젝트 루트 디렉토리에 `.pth` 형식의 RVC 모델 파일을 준비하세요.

예: `grandpa_model.pth`

### 2. 설정 수정

`main.py` 파일의 상단 설정 부분을 수정하세요:

```python
MODEL_PATH = "grandpa_model.pth"   # RVC 모델 파일 경로
INDEX_PATH = None                  # 인덱스 파일 경로 (없으면 None)
OUTPUT_FILE = "grandpa_result.wav" # 저장할 파일명
TEXT = "에잉, 비가 오려나 무릎이 시리구나. 밥은 먹었니?" # 변환할 텍스트
PITCH_SHIFT = -8                   # 피치 조절 (음수=저음, 양수=고음)
```

### 3. 실행

```bash
python main.py
```

## ⚙️ 설정 옵션

### PITCH_SHIFT (피치 조절)

- **음수 값** (-5 ~ -12): 목소리를 낮게 조절 (할아버지, 남성 목소리)
- **양수 값**: 목소리를 높게 조절 (여성, 어린이 목소리)
- **0**: 원본 피치 유지

### Edge-TTS 음성 선택

현재 코드는 `ko-KR-InJoonNeural` (한국어 남성 목소리)를 사용합니다. 다른 음성을 사용하려면 `main.py`의 `generate_base_tts` 함수를 수정하세요.

사용 가능한 한국어 음성:
- `ko-KR-InJoonNeural` (남성)
- `ko-KR-SunHiNeural` (여성)
- `ko-KR-YuJinNeural` (여성)

## 📁 프로젝트 구조

```
tts_rvc/
├── main.py              # 메인 실행 파일
├── requirements.txt     # 의존성 패키지 목록
├── README.md           # 프로젝트 설명서
├── .python-version     # Python 버전 설정
└── .venv/              # 가상환경 (생성됨)
```

## 🔧 문제 해결

### Python 3.11 사용 시 fairseq dataclass 에러 발생

Python 3.11에서는 `fairseq==0.12.2`의 dataclass와 호환성 문제가 있습니다. Python 3.10을 사용하세요.

에러 메시지:
```
ValueError: mutable default <class 'fairseq.dataclass.configs.CommonConfig'> for field common is not allowed: use default_factory
```

해결 방법: Python 3.10으로 다운그레이드

### pip 설치 중 에러 발생

`omegaconf` 패키지와의 호환성 문제로 pip 24.1 이상 버전에서는 설치가 실패할 수 있습니다. pip 24.0 이하 버전을 사용하세요.

### 모델 파일을 찾을 수 없음

`MODEL_PATH`에 지정한 `.pth` 파일이 프로젝트 루트 디렉토리에 있는지 확인하세요.

### GPU 사용

NVIDIA GPU가 있는 경우 자동으로 CUDA를 사용합니다. GPU가 없으면 CPU로 실행됩니다.

## 📚 참고 자료

- [RVC Python](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)
- [Edge-TTS](https://github.com/rany2/edge-tts)

