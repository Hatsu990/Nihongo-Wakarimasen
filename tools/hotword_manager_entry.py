from nihongo_wakarimasen.config import AppConfig
from nihongo_wakarimasen.hotword_manager import run_hotword_manager


if __name__ == "__main__":
    raise SystemExit(run_hotword_manager(AppConfig.from_env()))
