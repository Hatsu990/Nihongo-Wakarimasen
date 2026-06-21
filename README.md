# Nihongo Wakarimasen

Windows에서 Discord, Chrome 같은 앱의 소리를 캡처해서 일본어 음성을 한국어 자막으로 보여주는 듣기 보조 도구입니다.

## 기능

- Windows 앱/프로세스별 오디오 캡처
- 로컬 Japanese STT
- Papago 일본어 -> 한국어 번역
- 화면 위 오버레이 자막 표시
- 사용자 이름 사전과 Papago API 등록 GUI

## 설치

Python 3.10을 권장합니다.

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pip install -r requirements-gpu.txt
.\.venv\Scripts\python -m pip install -e .
```

로컬 STT 모델은 처음 실행할 때 자동으로 다운로드됩니다. 미리 받아두고 싶으면 아래 명령을 실행하세요.

```powershell
.\tools\preload_local_model.ps1
```

## Papago API 등록

사전 관리 창을 실행한 뒤 `Papago API` 탭에 Client ID와 Client Secret을 저장합니다.

```powershell
.\.venv\Scripts\python -m nihongo_wakarimasen --hotword-manager
```

저장된 API 키와 사용자 이름 사전은 Windows 사용자 데이터 폴더에 저장됩니다. GitHub 저장소와 배포 ZIP에는 포함되지 않습니다.

## 오버레이 실행

```powershell
.\tools\overlay_control.ps1 start
```

실행하면 어느 앱의 사운드를 가져올지 선택하는 창이 뜹니다. Discord, Chrome 등 번역할 앱을 선택하면 오버레이가 시작됩니다.

상태 확인과 종료:

```powershell
.\tools\overlay_control.ps1 status
.\tools\overlay_control.ps1 stop
```

## 이름 사전

사전 관리 창에서 이름, 히라가나, 가타카나, 한글 표시를 등록할 수 있습니다.

- 이름/히라가나/가타카나: STT 인식 힌트로 사용
- 한글 표시: Papago 번역 후처리 보정에 사용

사전 수정 후에는 오버레이를 다시 시작해야 반영됩니다.

## 진단

환경과 설정 확인:

```powershell
.\.venv\Scripts\python -m nihongo_wakarimasen --diagnose
```

소리 입력 확인:

```powershell
.\.venv\Scripts\python -m nihongo_wakarimasen --audio-meter --capture-process chrome.exe --seconds 5 --capture-interval 0.5
```

## 기본 로컬 STT 설정

`tools/overlay_control.ps1`의 기본값은 현재 실험 기준으로 맞춰져 있습니다.

- model: `kotoba-tech/kotoba-whisper-v2.0-faster`
- device: `cuda`
- compute type: `float16`
- beam size: `5`

GPU VRAM이 부족하면 `tools/overlay_control.ps1`에서 beam size를 낮추거나 더 가벼운 모델로 바꾸면 됩니다.

## 개인정보와 배포

공개 저장소에는 개인 이름 사전, 사용자 번역 보정 사전, Papago API 키, 로그가 올라가지 않도록 `.gitignore`로 제외합니다.

개인 데이터 기본 저장 위치:

```text
%APPDATA%\NihongoWakarimasen\
```

릴리즈 ZIP을 만들 때도 이 폴더의 파일은 포함하지 않습니다.
