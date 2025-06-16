# --- 簡略化版 constants.py (Streamlit用) ---

# デバッグモードフラグ
DEBUG = True

# アプリケーション設定
APP_CONFIG = {
    "title": "けっくるてぽこ - 物流特化型サポートエージェント",
    "version": "1.0.0",
    "author": "Logistics Support Team",
    "description": "AI搭載配送ルート最適化システム"
}

# API設定
API_CONFIG = {
    "gemini": {
        "model_name": "gemini-1.5-flash",
        "temperature": 0.2,
        "max_output_tokens": 4096,
        "top_p": 0.8,
        "top_k": 40
    },
    "google_maps": {
        "language": "ja",
        "units": "metric",
        "mode": "driving"
    }
}

# UI設定
UI_CONFIG = {
    "page_icon": "🤖",
    "layout": "wide",
    "sidebar_state": "expanded",
    "theme_color": "#48D1CC"
}

# データ検証設定
VALIDATION_CONFIG = {
    "min_locations": 2,
    "max_locations": 25,
    "max_prompt_length": 30000,
    "required_columns": [
        "地点", "地点コード", "住所", 
        "希望到着", "希望出発"
    ]
}

# エラーメッセージ
ERROR_MESSAGES = {
    "api_key_missing": "APIキーが設定されていません",
    "api_init_failed": "API初期化に失敗しました",
    "insufficient_locations": "最低2つの地点が必要です",
    "no_start_point": "始点フラグ(1)が設定されていません",
    "file_read_error": "ファイル読み込みエラー",
    "json_parse_error": "AI応答のJSON解析エラー",
    "maps_api_error": "Google Maps APIエラー",
    "gemini_api_error": "Gemini APIエラー"
}

# 成功メッセージ
SUCCESS_MESSAGES = {
    "api_initialized": "API初期化完了",
    "data_loaded": "データを読み込みました",
    "route_calculated": "ルート計算完了",
    "file_uploaded": "ファイルアップロード成功"
}

# デフォルト設定値
DEFAULT_SETTINGS = {
    "optimization_mode": "mode1",
    "allow_multiple_trucks": False,
    "use_tolls": True,
    "continuous_limit": True,
    "continuous_hours": 4,
    "rest_minutes": 30,
    "daily_limit": True,
    "daily_hours": 13
}

# 最適化モード定義
OPTIMIZATION_MODES = {
    "mode1": "おまかせ最適化(推奨)",
    "mode2": "最短距離を優先", 
    "mode3": "時間指定を厳守",
    "mode4": "カスタムプロンプト"
}

# ステータス定義
STATUS_TYPES = ["出発", "到着", "移動", "滞在", "休憩"]

# カラム設定
COLUMN_CONFIG = {
    "始点": {"type": "selectbox", "options": ["", "1"]},
    "終着": {"type": "selectbox", "options": ["", "1"]},
    "希望到着": {"type": "text", "format": "YYYY/MM/DD HH:MM"},
    "希望出発": {"type": "text", "format": "YYYY/MM/DD HH:MM"}
}