# --- 簡略化版 api_handler.py (Streamlit用) ---

import google.generativeai as genai
import googlemaps
import traceback
import streamlit as st

# グローバル変数
gmaps_client = None
gemini_model = None

def initialize_gmaps(api_key):
    """Google Maps APIクライアントの初期化"""
    global gmaps_client
    if not api_key:
        st.warning("Google Maps APIキーが設定されていません")
        gmaps_client = None
        return False
    
    try:
        gmaps_client = googlemaps.Client(key=api_key)
        # 簡単な接続テスト
        test_response = gmaps_client.geocode("Tokyo, Japan")
        if not test_response:
            st.error("Google Maps API接続テストに失敗しました")
            gmaps_client = None
            return False
        return True
    except Exception as e:
        st.error(f"Google Maps API初期化エラー: {e}")
        gmaps_client = None
        return False

def initialize_gemini(api_key):
    """Gemini APIの初期化"""
    global gemini_model
    if not api_key:
        st.warning("Gemini APIキーが設定されていません")
        gemini_model = None
        return False
    
    try:
        genai.configure(api_key=api_key)
        gemini_model = genai.GenerativeModel('gemini-1.5-flash')
        # 簡単な接続テスト
        test_response = gemini_model.generate_content(
            "テスト", 
            generation_config=genai.types.GenerationConfig(temperature=0.1)
        )
        if not test_response.text:
            st.error("Gemini API接続テストに失敗しました")
            gemini_model = None
            return False
        return True
    except Exception as e:
        st.error(f"Gemini API初期化エラー: {e}")
        gemini_model = None
        return False

def get_distance_matrix(locations, start_time, use_tolls):
    """距離マトリックスの取得"""
    if not gmaps_client:
        return {'status': 'ERROR', 'message': 'Google Mapsクライアントが初期化されていません。'}
    
    if not locations or len(locations) < 2:
        return {'status': 'ERROR', 'message': '最低2つの地点が必要です。'}
    
    addresses = [loc["住所"] for loc in locations if loc.get("住所")]
    if len(addresses) != len(locations):
        return {'status': 'ERROR', 'message': '全ての地点に住所が設定されている必要があります。'}
    
    departure_timestamp = int(start_time.timestamp())

    api_args = {
        "origins": addresses,
        "destinations": addresses,
        "mode": "driving",
        "departure_time": departure_timestamp,
        "language": "ja",
        "units": "metric"
    }

    if not use_tolls:
        api_args["avoid"] = "tolls"
    
    try:
        response = gmaps_client.distance_matrix(**api_args)
        
        # レスポンスの検証
        if response.get('status') != 'OK':
            return {
                'status': 'API_ERROR', 
                'message': f'Google Maps API エラー: {response.get("status", "UNKNOWN_ERROR")}'
            }
        
        # 各要素の検証
        for i, row in enumerate(response.get('rows', [])):
            for j, element in enumerate(row.get('elements', [])):
                if element.get('status') not in ['OK', 'ZERO_RESULTS']:
                    st.warning(f"警告: {addresses[i]} → {addresses[j]} のルートが見つかりません")
        
        return response
        
    except Exception as e:
        error_info = traceback.format_exc()
        st.error(f"Distance Matrix API呼び出しエラー: {str(e)}")
        return {'status': 'API_ERROR', 'message': str(e), 'traceback': error_info}

def get_ai_route_plan(prompt):
    """AIルートプランの取得"""
    if not gemini_model:
        return {'status': 'ERROR', 'message': 'Geminiモデルが初期化されていません。'}
    
    if not prompt or len(prompt.strip()) == 0:
        return {'status': 'ERROR', 'message': 'プロンプトが空です。'}
    
    try:
        # プロンプトの長さ制限チェック（約30,000文字）
        if len(prompt) > 30000:
            st.warning("プロンプトが長すぎます。簡略化して送信します。")
            prompt = prompt[:30000] + "..."
        
        response = gemini_model.generate_content(
            prompt, 
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=4096,
                top_p=0.8,
                top_k=40
            )
        )
        
        if not response.text:
            return {'status': 'API_ERROR', 'message': 'Gemini APIから空の応答が返されました。'}
        
        return {'status': 'OK', 'data': response.text}
        
    except Exception as e:
        error_info = traceback.format_exc()
        st.error(f"Gemini API呼び出しエラー: {str(e)}")
        return {'status': 'API_ERROR', 'message': str(e), 'traceback': error_info}

def validate_api_keys():
    """APIキーの有効性を検証"""
    results = {
        'gmaps': gmaps_client is not None,
        'gemini': gemini_model is not None
    }
    return results

def get_api_status():
    """API接続状況を取得"""
    status = {
        'google_maps': {
            'initialized': gmaps_client is not None,
            'client_type': type(gmaps_client).__name__ if gmaps_client else None
        },
        'gemini': {
            'initialized': gemini_model is not None,
            'model_name': gemini_model.model_name if gemini_model else None
        }
    }
    return status