# Nihongo Wakarimasen

Windows에서 Discord, Chrome 같은 앱의 소리를 캡처해서 일본어 음성을 한국어 자막으로 보여주는 듣기 보조 도구입니다.

## 설치방법

GitHub Releases에서 `Nihongo-Wakarimasen.zip`을 받은 뒤 압축을 풀고 아래 exe를 실행하면 됩니다.

1. `Download Local Model.exe`
   - 로컬 STT 모델을 미리 다운로드합니다.
   - 처음 한 번만 실행하면 됩니다.
   - `Model is ready.`가 보이면 완료입니다.

2. `Name Dictionary.exe`
   - `Papago API` 탭에 Client ID와 Client Secret을 저장합니다.
   - 필요하면 이름, 히라가나, 가타카나, 한글 표시를 등록합니다.

3. `Nihongo Wakarimasen.exe`
   - 실행하면 어느 앱의 사운드를 가져올지 선택하는 창이 뜹니다.
   - Discord, Chrome 등 번역할 앱을 선택하면 오버레이가 시작됩니다.

`Download Local Model.exe`를 건너뛰어도 오버레이 첫 실행 중 모델 다운로드가 시도될 수 있지만, 진행 상황을 보기 어렵기 때문에 먼저 실행하는 것을 권장합니다.

## 기능

- Windows 앱/프로세스별 오디오 캡처
- 로컬 Japanese STT
- Papago 일본어 -> 한국어 번역
- 화면 위 오버레이 자막 표시
- 사용자 이름 사전과 Papago API 등록 GUI

## 개인정보와 배포

사용자별 Papago API 키, 이름 사전, 사용자 번역 보정 사전은 Windows 사용자 데이터 폴더에 저장됩니다.

```text
%APPDATA%\NihongoWakarimasen\
```

GitHub 저장소와 릴리즈 ZIP에는 아래 파일을 포함하지 않습니다.

- 개인 이름 사전
- 사용자 번역 보정 사전
- Papago API 키
- 실행 로그

## 이름 사전

사전 관리 창에서 이름, 히라가나, 가타카나, 한글 표시를 등록할 수 있습니다.

- 이름/히라가나/가타카나: STT 인식 힌트로 사용
- 한글 표시: Papago 번역 후처리 보정에 사용

사전 수정 후에는 오버레이를 다시 시작해야 반영됩니다.

## 개발자용 실행

소스에서 직접 실행할 때는 Python 3.10을 권장합니다.

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pip install -r requirements-gpu.txt
.\.venv\Scripts\python -m pip install -e .
```

개발자용 오버레이 실행:

```powershell
.\tools\overlay_control.ps1 start
```

개발자용 사전 관리:

```powershell
.\.venv\Scripts\python -m nihongo_wakarimasen --hotword-manager
```

## 기본 로컬 STT 설정

릴리즈 exe와 `tools/overlay_control.ps1`의 기본값은 현재 실험 기준으로 맞춰져 있습니다.

- model: `kotoba-tech/kotoba-whisper-v2.0-faster`
- device: `cuda`
- compute type: `float16`
- beam size: `5`

NVIDIA GPU/드라이버가 없거나 VRAM이 부족한 PC에서는 로컬 STT 실행이 실패할 수 있습니다.
