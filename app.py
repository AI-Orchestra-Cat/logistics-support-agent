import streamlit as st
import pandas as pd
import json
import csv
import io
import re
from datetime import datetime, timedelta
import traceback
import webbrowser
import urllib.parse
from textwrap import dedent

# 既存モジュールのインポート
try:
    import api_handler
    from constants import DEBUG
except ImportError:
    st.error("必要なモジュール (api_handler.py, constants.py) が見つかりません。")
    st.stop()

# ページ設定
st.set_page_config(
    page_title="けっくるてぽこ - 物流サポートエージェント",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

#======================================================================
# 関数定義セクション
#======================================================================

def initialize_session_state():
    # セッション状態の初期化（改良版：月別API使用量対応）
    if 'api_initialized' not in st.session_state:
        st.session_state.api_initialized = False
    if 'optimization_results' not in st.session_state:
        st.session_state.optimization_results = None
    if 'input_data' not in st.session_state:
        st.session_state.input_data = pd.DataFrame()
    if 'vehicles' not in st.session_state:
        st.session_state.vehicles = []
    if 'api_usage_monthly' not in st.session_state:
        st.session_state.api_usage_monthly = {}

def setup_api_keys():
     # ロゴの表示
    st.sidebar.image("logo.png", width=200)
   
   
    # APIキーの設定（改良版：月別使用量管理 + 接続エラー対策）
    st.sidebar.header("🔑 API設定")
    
    # 接続状態の表示
    if 'last_activity' not in st.session_state:
        st.session_state.last_activity = datetime.now()
    
    # 長時間処理の警告
    time_since_activity = datetime.now() - st.session_state.last_activity
    if time_since_activity.total_seconds() > 300:  # 5分以上
        st.sidebar.warning("⚠️ 長時間経過。接続エラーの可能性があります。")
        if st.sidebar.button("🔄 セッションリフレッシュ"):
            for key in list(st.session_state.keys()):
                if key not in ['api_initialized', 'vehicles']:
                    del st.session_state[key]
            st.session_state.last_activity = datetime.now()
            st.rerun()
    
    gemini_key_secret = st.secrets.get("GEMINI_API_KEY", "")
    maps_key_secret = st.secrets.get("MAPS_API_KEY", "")

    gemini_key = st.sidebar.text_input("Gemini APIキー", value=gemini_key_secret, type="password")
    maps_key = st.sidebar.text_input("Google Maps APIキー", value=maps_key_secret, type="password")

    if st.sidebar.button("APIキーを適用", use_container_width=True):
        if gemini_key and maps_key:
            with st.spinner("APIを初期化中..."):
                gemini_success = api_handler.initialize_gemini(gemini_key)
                maps_success = api_handler.initialize_gmaps(maps_key)
                if gemini_success and maps_success:
                    st.session_state.api_initialized = True
                    st.success("✅ API初期化完了")
                    st.rerun()
                else:
                    st.session_state.api_initialized = False
                    st.error("❌ API初期化失敗")
        else:
            st.warning("両方のAPIキーを入力してください。")

    if st.session_state.api_initialized:
        st.sidebar.success("✅ API使用可能")
        
        # 月別使用量管理
        current_month = datetime.now().strftime("%Y-%m")
        if current_month not in st.session_state.api_usage_monthly:
            st.session_state.api_usage_monthly[current_month] = {"gemini": 0, "maps": 0}
        
        usage = st.session_state.api_usage_monthly[current_month]
        st.sidebar.metric(f"Gemini API使用 ({current_month})", f"{usage['gemini']}回")
        st.sidebar.metric(f"Maps API使用 ({current_month})", f"{usage['maps']}回")
        
        # 累計表示
        total_gemini = sum([monthly["gemini"] for monthly in st.session_state.api_usage_monthly.values()])
        total_maps = sum([monthly["maps"] for monthly in st.session_state.api_usage_monthly.values()])
        st.sidebar.metric("Gemini API累計", f"{total_gemini}回")
        st.sidebar.metric("Maps API累計", f"{total_maps}回")

    return st.session_state.api_initialized

def vehicle_master_section():
    # サイドバーに車両マスタ管理UIを表示する（修正版：拠点→所属）
    st.sidebar.header("🚚 車両マスタ管理")
    if 'vehicles' not in st.session_state or not st.session_state.vehicles:
         st.session_state.vehicles = [
            {"車両ID": "T01", "車種名": "4tトラック", "最大積載重量": 4000, "最大積載容量": 20, "所属": "東京営業所", "車両ステータス": "稼働中", "メモ欄": "定期メンテ済み"}
        ]

    try:
        df_vehicles = pd.DataFrame(st.session_state.vehicles)
        edited_df = st.sidebar.data_editor(
            df_vehicles, key="vehicle_editor", num_rows="dynamic", use_container_width=True,
            column_config={
                "車両ステータス": st.column_config.SelectboxColumn("車両ステータス", options=["稼働中", "待機中", "整備中"], required=True),
                "最大積載重量": st.column_config.NumberColumn(format="%d kg"),
                "最大積載容量": st.column_config.NumberColumn(format="%d m³"),
            }
        )
        if not edited_df.equals(df_vehicles):
            st.session_state.vehicles = edited_df.to_dict('records')
            st.success("車両情報を更新しました。")
            st.rerun()
    except Exception as e:
        st.sidebar.error(f"車両マスタ表示エラー: {e}")

def vehicle_selection_section():
    # メイン画面に投入車両の選択UIを表示する（修正版：拠点→所属）
    st.header("1. 投入車両の選択")
    available_vehicles = [v for v in st.session_state.vehicles if v.get("車両ステータス") == "稼働中"]
    
    if not available_vehicles:
        st.warning("現在、稼働中の車両が登録されていません。")
        return None

    df_vehicles = pd.DataFrame(available_vehicles)
    df_vehicles['選択'] = False
    
    selected_df = st.data_editor(
        df_vehicles, use_container_width=True, hide_index=True,
        column_order=("選択", "車両ID", "車種名", "最大積載重量", "最大積載容量", "所属", "メモ欄"),
        disabled=("車両ID", "車種名", "最大積載重量", "最大積載容量", "所属", "メモ欄", "車両ステータス")
    )
    
    used_vehicles = selected_df[selected_df['選択'] == True]
    if not used_vehicles.empty:
        return used_vehicles
    return None

def generate_sample_data():
    # サンプル配送データを生成
    today = (datetime.now() + timedelta(days=1)).strftime("%Y/%m/%d")
    sample_data = [
        {"始点": "1", "終着": "", "地点": "サンプル丸の内", "地点コード": "T001", "住所": "東京都千代田区丸の内１丁目", "希望到着": f"{today} 08:30", "希望出発": f"{today} 09:00", "積み込み重量": 0, "積み込み容量": 0, "荷下ろし重量": 0, "荷下ろし容量": 0, "備考": "特になし"},
        {"始点": "", "終着": "", "地点": "サンプル西新宿", "地点コード": "T002", "住所": "東京都新宿区西新宿２丁目", "希望到着": f"{today} 10:00", "希望出発": f"{today} 10:30", "積み込み重量": 100, "積み込み容量": 1, "荷下ろし重量": 0, "荷下ろし容量": 0, "備考": "時間厳守"},
        {"始点": "", "終着": "2", "地点": "サンプル札幌", "地点コード": "H001", "住所": "北海道札幌市中央区北1条西2丁目", "希望到着": "", "希望出発": "", "積み込み重量": 0, "積み込み容量": 0, "荷下ろし重量": 100, "荷下ろし容量": 1, "備考": "フェリー利用想定"}
    ]
    return pd.DataFrame(sample_data)

def data_input_section():
    # データ入力セクション（エラーハンドリング強化版）
    st.header("2. 配送先の入力")
    REQUIRED_COLUMNS = ["始点", "終着", "地点", "地点コード", "住所", "希望到着", "希望出発", "積み込み重量", "積み込み容量", "荷下ろし重量", "荷下ろし容量", "備考"]
    
    # メトリクス表示を復活
    if 'input_data' in st.session_state and not st.session_state.input_data.empty:
        try:
            input_df = st.session_state.input_data
            start_count = sum(1 for _, row in input_df.iterrows() if str(row.get("始点", "")).strip() == "1")
            end_count = sum(1 for _, row in input_df.iterrows() if str(row.get("終着", "")).strip() == "2")
            
            col1, col2, col3 = st.columns(3)
            with col1: 
                st.markdown("### 📍 始点数合計")
                st.markdown(f"**{start_count}**")
            with col2: 
                st.markdown("### 🏁 終着数合計")
                st.markdown(f"**{end_count}**")
            with col3: 
                st.markdown("### 📋 総地点数合計")
                st.markdown(f"**{len(input_df)}**")
            st.markdown("---")
        except Exception as e:
            st.error(f"❌ データ処理エラー: {str(e)}")
    
    if 'input_data' not in st.session_state or st.session_state.input_data.empty:
        st.session_state.input_data = generate_sample_data()

    tab1, tab2 = st.tabs(["✏️ 手動入力", "📁 ファイルアップロード"])
    
    with tab1:
        edited_df = st.data_editor(
            st.session_state.input_data, use_container_width=True, num_rows="dynamic", key="data_editor",
            column_config={
                "始点": st.column_config.SelectboxColumn("始点", options=["", "1"]), 
                "終着": st.column_config.SelectboxColumn("終着", options=["", "2"]),
            }
        )
        if not edited_df.equals(st.session_state.input_data):
            st.session_state.input_data = edited_df
            st.rerun()
    
    with tab2:
        uploaded_file = st.file_uploader("配送先データファイル", type=['csv'])
        if uploaded_file is not None:
            try:
                # CSV読み込み（エンコーディング自動判定）
                try:
                    df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
                except UnicodeDecodeError:
                    try:
                        df = pd.read_csv(uploaded_file, encoding='shift_jis')
                    except UnicodeDecodeError:
                        df = pd.read_csv(uploaded_file, encoding='utf-8')
                
                # 必須列の存在チェック
                missing_columns = set(REQUIRED_COLUMNS) - set(df.columns)
                if missing_columns:
                    st.error(f"❌ 必須列が不足: {', '.join(missing_columns)}")
                    st.info("💡 必要な列名一覧:")
                    for col in REQUIRED_COLUMNS:
                        st.write(f"• {col}")
                    return st.session_state.input_data
                
                st.session_state.input_data = df[REQUIRED_COLUMNS]
                st.success(f"✅ {len(df)}件のデータを読み込みました")
                st.rerun()
            except Exception as e:
                st.error(f"❌ ファイル読み込みエラー: {e}")
    
    return st.session_state.input_data

def optimization_settings():
    # 最適化設定セクション（復活版・完全修正）
    st.header("⚙️ 条件設定")
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("基本設定")
        # 最適化目標の選択肢を正しく設定
        optimization_options = [
            ("おまかせ最適化(推奨)", "mode1"), 
            ("最短距離を優先", "mode2"), 
            ("時間指定を厳守", "mode3"), 
            ("カスタムプロンプト", "mode4")
        ]
        selected_option = st.selectbox(
            "最適化目標", 
            optimization_options, 
            format_func=lambda x: x[0]
        )
        optimization_mode = selected_option[1]
        
        use_tolls = st.checkbox("有料道路を使用", value=True)
    
    with col2:
        st.subheader("労働条件設定")
        continuous_limit = st.checkbox("連続運転時間制限", value=True)
        continuous_hours, rest_minutes = (0, 0)
        if continuous_limit:
            col2_1, col2_2 = st.columns(2)
            with col2_1: 
                continuous_hours = st.number_input("連続運転時間(時間)", value=4, min_value=1, max_value=8)
            with col2_2: 
                rest_minutes = st.number_input("休憩時間(分)", value=30, min_value=15, max_value=60)
        
        daily_limit = st.checkbox("1日拘束時間制限", value=True)
        daily_hours = 0
        if daily_limit:
            daily_hours = st.number_input("1日拘束時間(時間)", value=13, min_value=8, max_value=16)
    
    # カスタムプロンプト入力エリア
    custom_prompt = ""
    if optimization_mode == "mode4":
        st.subheader("カスタムプロンプト")
        custom_prompt = st.text_area(
            "カスタム指示を入力", 
            height=150, 
            placeholder="例: 午前中は住宅地を優先し、午後は商業地を回ってください。"
        )
    
    return {
        "mode": optimization_mode, 
        "use_tolls": use_tolls, 
        "continuous_limit": continuous_limit, 
        "continuous_hours": continuous_hours, 
        "rest_minutes": rest_minutes, 
        "daily_limit": daily_limit, 
        "daily_hours": daily_hours, 
        "custom_prompt": custom_prompt
    }

def analyze_vehicle_requirements(input_data):
    """時間制約から必要車両数を自動判断"""
    from datetime import datetime
    import pandas as pd
    
    time_slots = []
    for loc in input_data:
        arrival_str = loc.get('希望到着', '')
        departure_str = loc.get('希望出発', '')
        
        if arrival_str and departure_str:
            try:
                arrival_time = pd.to_datetime(arrival_str)
                departure_time = pd.to_datetime(departure_str)
                time_slots.append({
                    'location': loc.get('地点', ''),
                    'arrival': arrival_time,
                    'departure': departure_time,
                    'location_code': loc.get('地点コード', '')
                })
            except:
                continue
    
    # 時間重複を検出
    conflicts = []
    for i, slot1 in enumerate(time_slots):
        for j, slot2 in enumerate(time_slots[i+1:], i+1):
            # 時間重複の判定
            if (slot1['arrival'] < slot2['departure'] and slot2['arrival'] < slot1['departure']):
                conflicts.append((slot1, slot2))
    
    min_vehicles_needed = 1
    if conflicts:
        # 単純化：重複がある場合は最低2台必要
        min_vehicles_needed = len(conflicts) + 1
    
    return min_vehicles_needed, conflicts

def get_available_vehicles_for_ai(selected_vehicles, all_vehicles, min_required):
    """AI用に利用可能車両を準備（修正版：所属情報を除外）"""
    # 選択された車両
    selected_count = len(selected_vehicles)
    
    # 不足している場合は追加で利用可能車両を含める
    if selected_count < min_required:
        available_vehicles = [v for v in all_vehicles if v.get("車両ステータス") == "稼働中"]
        # 選択済み車両の車両IDを取得
        selected_ids = set(selected_vehicles['車両ID'].tolist())
        
        # 追加で利用可能な車両を含める
        additional_vehicles = []
        for vehicle in available_vehicles:
            if vehicle['車両ID'] not in selected_ids:
                additional_vehicles.append(vehicle)
                if len(selected_vehicles) + len(additional_vehicles) >= min_required:
                    break
        
        # 選択済み + 追加車両を結合
        all_available = pd.concat([
            selected_vehicles,
            pd.DataFrame(additional_vehicles)
        ], ignore_index=True)
        
        # 所属、選択、メモ欄を除外してAIに送信
        return all_available.drop(columns=['選択', 'メモ欄', '所属'], errors='ignore')
    
    # 所属、選択、メモ欄を除外してAIに送信
    return selected_vehicles.drop(columns=['選択', 'メモ欄', '所属'], errors='ignore')

def generate_prompt_preview(selected_vehicles, all_vehicles, input_data, settings):
    # プレビュー用プロンプトを生成（修正版：所属情報を除外）
    prompt_parts = []
    
    # 必要車両数の自動判断
    min_required, conflicts = analyze_vehicle_requirements(input_data)
    vehicles_for_ai = get_available_vehicles_for_ai(selected_vehicles, all_vehicles, min_required)
    
    # 片道輸送の明確化を最優先で配置
    transport_method_clarification = """## 🎯 最重要・輸送方式の明確化
これは片道輸送です。始点から終着点への一方向移動のみを行い、往復・巡回・帰還は一切行いません。
終着地で業務を完了し、始点に戻る必要はありません。

## 🚚 交通手段について
移動には自動車(トラック・バン等の道路輸送)を使用してください。必要に応じて船舶(フェリー)との併用も可能です。
ただし、航空便、貨物列車、宅配便等の利用はできません。

"""
    
    if settings["mode"] == "mode4":
        prompt_parts.append(f"""# 役割
あなたは、物流業界で豊富な経験を持つ配車計画の専門家です。

{transport_method_clarification}

# 最重要・お客様からの特別なご要望
以下のご指示を、他のどのような条件よりも優先して実行してください。

{settings["custom_prompt"]}
""")
    else:
        prompt_parts.append(f"""# 役割
あなたは、物流業界で豊富な経験を持つ配車計画の専門家です。

{transport_method_clarification}

# 文脈・状況について""")
        
        # 複数車両必要性の自動判断結果を含める
        if min_required > 1:
            prompt_parts.append(f"時間制約の分析により、最低{min_required}台の車両が必要です。")
            if conflicts:
                prompt_parts.append("以下の時間重複が検出されました：")
                for conflict in conflicts:
                    prompt_parts.append(f"- {conflict[0]['location']}と{conflict[1]['location']}が同時間帯に重複")
        
        prompt_parts.append(f"利用可能な{len(vehicles_for_ai)}台の車両から最適な配車計画を立ててください。")
        
        if settings["use_tolls"]:
            prompt_parts.append("移動の際は、有料道路も利用して構いません。")
        else:
            prompt_parts.append("なお、移動時は有料道路を避けるルートでお願いします。")
        
        # 労働条件を自然な文章で追加
        if settings["continuous_limit"] or settings["daily_limit"]:
            prompt_parts.append("\n\nドライバーの労働環境にも十分配慮していただき、")
            labor_conditions = []
            if settings["continuous_limit"]:
                labor_conditions.append(f"連続運転時間は{settings['continuous_hours']}時間以内")
            if settings["daily_limit"]:
                labor_conditions.append(f"1日の全体拘束時間は{settings['daily_hours']}時間以内")
            prompt_parts.append("、".join(labor_conditions) + "となるよう計画していただけますでしょうか。")
        
        prompt_parts.append("\n\n# 今回の計画で最も重視していただきたいポイント")
        if settings["mode"] == "mode1":
            prompt_parts.append("全体の移動時間をできる限り短縮することを最優先にお考えください。")
        elif settings["mode"] == "mode2":
            prompt_parts.append("総走行距離を最小限に抑えることを最優先にお考えください。")
        elif settings["mode"] == "mode3":
            prompt_parts.append("各訪問先の希望到着・出発時刻をできる限り厳守することを最優先にお考えください。")

    prompt_parts.append("\n\n# 制約・条件")
    prompt_parts.append("## 働き方に関する重要規則")
    prompt_parts.append("### フェリー特例")
    prompt_parts.append("以下の規則を厳密に遵守してください。")
    prompt_parts.append("- フェリー乗船時間は、原則として、休息期間として取り扱います。")
    prompt_parts.append("- フェリー乗船時間が8時間を超える場合には、原則としてフェリー下船時刻から次の勤務が開始される（勤務日がリセットされる）ものとします。この場合、計画が複数日にまたがっても構いません。")
    prompt_parts.append("- **重要**: フェリー乗船中の休憩時間は、具体的な開始時刻と終了時刻を明記してください。")
    prompt_parts.append("- **例**: 11:00乗船、翌日06:00下船の場合 → 23:00-06:00を「フェリー乗船中休息」として明記")
    prompt_parts.append("- **重要**: フェリー乗船中の休憩時間は、具体的な開始時刻と終了時刻を明記してください。")
    prompt_parts.append("- **例**: 11:00乗船、翌日06:00下船の場合 → 23:00-06:00を「フェリー乗船中休息」として明記")
    
    prompt_parts.append("\n### ⚠️ 重要：実在する交通インフラのみ使用")
    prompt_parts.append("**絶対に架空の港や航路を作らないでください。**")
    prompt_parts.append("実在するフェリー航路のみ：")
    prompt_parts.append("- 本州↔北海道: 大間港↔函館港（1時間30分）、青森港↔函館港（3時間40分）、八戸港↔苫小牧港（8時間）")
    prompt_parts.append("- 本州↔九州: 別府港↔八幡浜港、新門司港↔大阪南港")
    prompt_parts.append("- 本州↔四国: 高松港↔宇野港、小豆島航路")
    prompt_parts.append("**重要**: 東京↔札幌の直通フェリーは存在しません。北海道への移動は陸路で本州フェリー港まで移動後、フェリーで北海道の港へ、その後陸路で目的地という経路になります。")
    prompt_parts.append("**札幌港、東京港などの架空の港は絶対に使用しないでください。**")
    
    prompt_parts.append("\n### ⚠️ 重要：実在する交通インフラのみ使用")
    prompt_parts.append("**絶対に架空の港や航路を作らないでください。**")
    prompt_parts.append("実在するフェリー航路のみ：")
    prompt_parts.append("- 本州↔北海道: 大間港↔函館港（1時間30分）、青森港↔函館港（3時間40分）、八戸港↔苫小牧港（8時間）")
    prompt_parts.append("- 本州↔九州: 別府港↔八幡浜港、新門司港↔大阪南港")
    prompt_parts.append("- 本州↔四国: 高松港↔宇野港、小豆島航路")
    prompt_parts.append("**重要**: 東京↔札幌の直通フェリーは存在しません。北海道への移動は陸路で本州フェリー港まで移動後、フェリーで北海道の港へ、その後陸路で目的地という経路になります。")
    prompt_parts.append("**札幌港、東京港などの架空の港は絶対に使用しないでください。**")

    # 重要：複数車両使用の指示を明確化
    prompt_parts.append("\n## 🚛 車両使用に関する最重要な指示")
    prompt_parts.append("- **同時刻に複数地点での作業が必要な場合は、必ず異なる車両に割り当ててください**")
    prompt_parts.append("- **1台の車両が同時に2箇所にいることは物理的に不可能です**")
    prompt_parts.append("- **時間制約により複数車両が必要な場合は、積極的に複数車両を使用してください**")
    prompt_parts.append("- **物理的に不可能なスケジュールの場合は、警告をサマリーに含めてください**")

    prompt_parts.append("\n## 利用可能な車両情報")
    prompt_parts.append(vehicles_for_ai.to_markdown(index=False))

    prompt_parts.append("\n## 訪問地点の詳細情報")
    prompt_parts.append("| 始点 | 終着 | 地点 | 地点コード | 住所 | 希望到着 | 希望出発 | 積込kg | 積込m3 | 荷卸kg | 荷卸m3 |")
    prompt_parts.append("|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|")
    
    for loc in input_data:
        # 備考欄を除外したテーブル生成（プレビュー版でも同様）
        row_str = f"| {loc.get('始点', '')} | {loc.get('終着', '')} | {loc.get('地点', '')} | {loc.get('地点コード', '')} | {loc.get('住所', '')} | {loc.get('希望到着', '')} | {loc.get('希望出発', '')} | {loc.get('積み込み重量', 0)} | {loc.get('積み込み容量', 0)} | {loc.get('荷下ろし重量', 0)} | {loc.get('荷下ろし容量', 0)} |"
        prompt_parts.append(row_str)

    prompt_parts.append("\n## 地点間の移動時間と距離について")
    prompt_parts.append("※実際の実行時には、Google Maps APIから取得したリアルタイムの交通情報を含む詳細データが追加されます。")

    prompt_parts.append("""
# タスク
上記の全ての条件を満たす、最適な片道輸送計画を作成してください。

# 重要な計画要件
1. **始点拠点への到着**: 始点拠点（出発地）にも到着時刻を設定してください（荷物の引き取り作業のため）
2. **適切な休憩**: 連続運転時間制限やフェリー特例に応じて、必要な休憩や休息期間を計画に含めてください
3. **全拠点の訪問**: 始点から各経由地を通って終着点まで、すべての拠点を効率的に巡回してください
4. **終着点の扱い**: 終着点（`終着`フラグが2の地点）の扱いは、入力データに従ってください
5. **⚠️ 最重要：時間制約の厳守**: 同時刻に複数地点での作業が必要な場合は、必ず複数車両を使用してください

# 出力形式についてのお願い
1. まず最初に、計画全体の要点を簡潔にまとめたサマリーコメントを日本語で記述してください。
   - **重要**: 複数車両が必要な理由がある場合は、その旨と根拠をサマリーに必ず含めてください
   - **重要**: 物理的に不可能な時間指定がある場合は、警告をサマリーに必ず含めてください
   - **重要**: フェリー特例を適用した場合（例：乗船時間を休息期間とした、勤務をリセットした等）は、その旨と法的根拠をサマリーに必ず含めてください
2. 次に、必ず改行して区切り線`---`を一行だけ出力してください。
3. 最後に、運行計画の詳細をJSONオブジェクトのリストとして出力してください。
4. **最重要:** JSONの各オブジェクトには、**必ず** `d`, `proposed_time`, `desired_time`, `time_difference`, `status`, `location_id`, `name_code`, `location_name`, `remarks` のキーを**すべて含めてください**。値がない場合は空文字 `""` を入れること。
5. `status` キーの値は、必ず「出発」「到着」「移動」「滞在」「休憩」「フェリー乗船」「フェリー移動」「フェリー下船」「フェリー乗船中休息」のいずれかを使用すること。
6. **始点拠点には「到着」ステータスを必ず含める**こと（荷物引き取りのため）
7. **必要に応じて「休憩」やフェリー関連のステータスを適切に配置**すること。

```json
[
    {
        "d": "トラック1",
        "proposed_time": "YYYY/MM/DD HH:MM",
        "desired_time": "YYYY/MM/DD HH:MM", 
        "time_difference": "HH:MM",
        "status": "到着",
        "location_id": "",
        "name_code": "地点コード",
        "location_name": "地点名",
        "remarks": "始点拠点への到着（荷物引き取り）"
    }
]
```""")
    
    return "\n".join(prompt_parts)

def calculate_route(vehicles, input_data, settings):
    # ルート計算の実行（修正版：所属情報を除外）
    numeric_columns = ["積み込み重量", "積み込み容量", "荷下ろし重量", "荷下ろし容量"]
    locations = []
    
    for row in input_data:
        loc = {}
        for key, value in row.items():
            # 備考欄は人間用のため、AIには送信しない
            if key == '備考':
                continue
            if key in numeric_columns:
                try: 
                    loc[key] = float(value) if pd.notna(value) and value != '' else 0.0
                except (ValueError, TypeError): 
                    loc[key] = 0.0
            else: 
                loc[key] = str(value) if pd.notna(value) else ""
        locations.append(loc)
    
    # 始点・終着の存在チェック
    start_locations = [loc for loc in locations if loc.get("始点") == '1']
    end_locations = [loc for loc in locations if loc.get("終着") == '2']
    
    if not start_locations: 
        raise ValueError("始点フラグ(1)が設定されていません")
    if not end_locations:
        raise ValueError("終着フラグ(2)が設定されていません")
    
    start_location = start_locations[0]
    try: 
        departure_dt = pd.to_datetime(start_location.get("希望出発", "")).to_pydatetime()
    except (ValueError, TypeError): 
        departure_dt = datetime.now() + timedelta(hours=1)

    with st.spinner("🗺️ 地点間の距離と時間を計算中..."):
        matrix = api_handler.get_distance_matrix(locations, departure_dt, settings["use_tolls"])
        
        # API使用量の計算
        current_month = datetime.now().strftime("%Y-%m")
        if current_month not in st.session_state.api_usage_monthly:
            st.session_state.api_usage_monthly[current_month] = {"gemini": 0, "maps": 0}
        
        maps_calls = len(locations) * len(locations)
        st.session_state.api_usage_monthly[current_month]["maps"] += maps_calls
        
    if not matrix or matrix.get('status') != 'OK': 
        raise Exception(f"Google Maps API エラー: {matrix.get('message', '不明なエラー')}")

    # 車両マスタから全車両情報を取得
    all_vehicles = st.session_state.vehicles
    
    # 改良されたプロンプト生成（所属情報除外版）
    prompt = generate_prompt(vehicles, all_vehicles, locations, matrix, settings)

    with st.spinner("🤖 AIが最適なルートを思考中..."):
        ai_response = api_handler.get_ai_route_plan(prompt)
        current_month = datetime.now().strftime("%Y-%m")
        if current_month in st.session_state.api_usage_monthly:
            st.session_state.api_usage_monthly[current_month]["gemini"] += 1
            
    if not ai_response or ai_response.get('status') != 'OK': 
        raise Exception(f"Gemini API エラー: {ai_response.get('message', '不明なエラー')}")

    processed_results, summary_text = process_ai_response(ai_response, locations)
    return processed_results, summary_text, prompt

def generate_prompt(selected_vehicles, all_vehicles, locations, matrix, settings):
    # AI実行用プロンプト生成（修正版：所属情報を除外）
    prompt_parts = []
    
    # 必要車両数の自動判断
    input_data_for_analysis = []
    for loc in locations:
        input_data_for_analysis.append({
            '地点': loc.get('地点', ''),
            '地点コード': loc.get('地点コード', ''),
            '希望到着': loc.get('希望到着', ''),
            '希望出発': loc.get('希望出発', '')
        })
    
    min_required, conflicts = analyze_vehicle_requirements(input_data_for_analysis)
    vehicles_for_ai = get_available_vehicles_for_ai(selected_vehicles, all_vehicles, min_required)
    
    # 片道輸送の明確化と車両設定
    transport_method_clarification = """## 🎯 最重要・輸送方式の明確化
これは片道輸送です。始点から終着点への一方向移動のみを行い、往復・巡回・帰還は一切行いません。
終着地で業務を完了し、始点に戻る必要はありません。

## 🚚 交通手段について
移動には自動車(トラック・バン等の道路輸送)を使用してください。必要に応じて船舶(フェリー)との併用も可能です。
ただし、航空便、貨物列車、宅配便等の利用はできません。

"""

    if settings["mode"] == "mode4":
        prompt_parts.append(f"""# 役割
あなたは、物流業界で豊富な経験を持つ配車計画の専門家です。

{transport_method_clarification}

# 最重要・お客様からの特別なご要望
以下のご指示を、他のどのような条件よりも優先して実行してください。

{settings["custom_prompt"]}
""")
    else:
        prompt_parts.append(f"""# 役割
あなたは、物流業界で豊富な経験を持つ配車計画の専門家です。

{transport_method_clarification}

# 文脈・状況について""")
        
        # 複数車両必要性の自動判断結果を含める
        if min_required > 1:
            prompt_parts.append(f"⚠️ 重要：時間制約の分析により、最低{min_required}台の車両が必要です。")
            if conflicts:
                prompt_parts.append("以下の時間重複が検出されました：")
                for conflict in conflicts:
                    prompt_parts.append(f"- {conflict[0]['location']}({conflict[0]['arrival'].strftime('%H:%M')}-{conflict[0]['departure'].strftime('%H:%M')})と{conflict[1]['location']}({conflict[1]['arrival'].strftime('%H:%M')}-{conflict[1]['departure'].strftime('%H:%M')})が重複")
        
        prompt_parts.append(f"利用可能な{len(vehicles_for_ai)}台の車両から最適な配車計画を立ててください。")
        
        if settings["use_tolls"]:
            prompt_parts.append("移動の際は、有料道路も利用して構いません。")
        else:
            prompt_parts.append("なお、移動時は有料道路を避けるルートでお願いします。")
        
        if settings["continuous_limit"] or settings["daily_limit"]:
            prompt_parts.append("\n\nドライバーの労働環境にも十分配慮していただき、")
            labor_conditions = []
            if settings["continuous_limit"]:
                labor_conditions.append(f"連続運転時間は{settings['continuous_hours']}時間以内")
            if settings["daily_limit"]:
                labor_conditions.append(f"1日の全体拘束時間は{settings['daily_hours']}時間以内")
            prompt_parts.append("、".join(labor_conditions) + "となるよう計画していただけますでしょうか。")
        
        # 最適化目標を自然な文章で明確化
        prompt_parts.append("\n\n# 今回の計画で最も重視していただきたいポイント")
        if settings["mode"] == "mode1":
            prompt_parts.append("全体の移動時間をできる限り短縮することを最優先にお考えください。")
        elif settings["mode"] == "mode2":
            prompt_parts.append("総走行距離を最小限に抑えることを最優先にお考えください。")
        elif settings["mode"] == "mode3":
            prompt_parts.append("各訪問先の希望到着・出発時刻をできる限り厳守することを最優先にお考えください。")
    
    # 重要：複数車両使用の指示を明確化
    prompt_parts.append("\n## 🚛 車両使用に関する重要な指示")
    prompt_parts.append("- 時間制約により複数車両が必要な場合は、積極的に複数車両を使用してください")
    prompt_parts.append("- 同時刻に複数地点での作業が必要な場合は、必ず異なる車両に割り当ててください")
    prompt_parts.append("- 物理的に不可能なスケジュールの場合は、実現可能な代替案を提示してください")
    
    prompt_parts.append("\n## 利用可能な車両情報")
    prompt_parts.append(vehicles_for_ai.to_markdown(index=False))
    
    prompt_parts.append("\n## 訪問地点の詳細情報")
    prompt_parts.append("| 始点 | 終着 | 地点 | 地点コード | 住所 | 希望到着 | 希望出発 | 積込kg | 積込m3 | 荷卸kg | 荷卸m3 |")
    prompt_parts.append("|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|")
    
    for loc in locations:
        # 備考欄を除外したテーブル生成
        row_str = f"| {loc.get('始点', '')} | {loc.get('終着', '')} | {loc.get('地点', '')} | {loc.get('地点コード', '')} | {loc.get('住所', '')} | {loc.get('希望到着', '')} | {loc.get('希望出発', '')} | {loc.get('積み込み重量', 0)} | {loc.get('積み込み容量', 0)} | {loc.get('荷下ろし重量', 0)} | {loc.get('荷下ろし容量', 0)} |"
        prompt_parts.append(row_str)
    
    prompt_parts.append("\n## 地点間の移動時間と距離の詳細データ")
    for i, origin in enumerate(locations):
        prompt_parts.append(f"### {origin.get('地点', '')} からの移動時間・距離:")
        for j, dest in enumerate(locations):
            if i == j: 
                continue
            element = matrix['rows'][i]['elements'][j]
            if element['status'] == 'OK': 
                prompt_parts.append(f"- {dest.get('地点', '')} まで: {element['duration']['text']} ({element['distance']['text']})")

    prompt_parts.append("""
# タスク
上記の全ての条件を満たす、最適な片道輸送計画を作成してください。

# 重要な計画要件
1. **始点拠点への到着**: 始点拠点（出発地）にも到着時刻を設定してください（荷物の引き取り作業のため）
2. **適切な休憩**: 連続運転時間制限やフェリー特例に応じて、必要な休憩や休息期間を計画に含めてください
3. **全拠点の訪問**: 始点から各経由地を通って終着点まで、すべての拠点を効率的に巡回してください
4. **終着点の扱い**: 終着点（`終着`フラグが2の地点）の扱いは、入力データに従ってください
5. **⚠️ 最重要：時間制約の厳守**: 同時刻に複数地点での作業が必要な場合は、必ず複数車両を使用してください

# 出力形式についてのお願い
1. まず最初に、計画全体の要点を簡潔にまとめたサマリーコメントを日本語で記述してください。
   - **重要**: 複数車両が必要な理由がある場合は、その旨と根拠をサマリーに必ず含めてください
   - **重要**: 物理的に不可能な時間指定がある場合は、警告をサマリーに必ず含めてください
   - **重要**: フェリー特例を適用した場合（例：乗船時間を休息期間とした、勤務をリセットした等）は、その旨と法的根拠をサマリーに必ず含めてください
2. 次に、必ず改行して区切り線`---`を一行だけ出力してください。
3. 最後に、運行計画の詳細をJSONオブジェクトのリストとして出力してください。
4. **最重要:** JSONの各オブジェクトには、**必ず** `d`, `proposed_time`, `desired_time`, `time_difference`, `status`, `location_id`, `name_code`, `location_name`, `remarks` のキーを**すべて含めてください**。値がない場合は空文字 `""` を入れること。
5. `status` キーの値は、必ず「出発」「到着」「移動」「滞在」「休憩」「フェリー乗船」「フェリー移動」「フェリー下船」のいずれかを使用すること。
6. **始点拠点には「到着」ステータスを必ず含める**こと（荷物引き取りのため）
7. **必要に応じて「休憩」やフェリー関連のステータスを適切に配置**すること。

```json
[
    {
        "d": "トラック1",
        "proposed_time": "YYYY/MM/DD HH:MM",
        "desired_time": "YYYY/MM/DD HH:MM", 
        "time_difference": "HH:MM",
        "status": "到着",
        "location_id": "",
        "name_code": "地点コード",
        "location_name": "地点名",
        "remarks": "始点拠点への到着（荷物引き取り）"
    }
]
```""")
    
    return "\n".join(prompt_parts)

def process_ai_response(ai_response, locations):
    # AI応答の処理（CSV出力バグ修正版）
    raw_data = ai_response.get('data', '')
    summary_text, _, json_part = raw_data.partition('---')
    summary_text = summary_text.strip()
    json_part = json_part.strip()

    try:
        json_str_match = re.search(r'```json\n(.*?)\n```', json_part, re.DOTALL)
        json_str = json_str_match.group(1) if json_str_match else json_part
        
        if not (json_str and json_str.strip().startswith('[')):
            return [], f"AI応答のJSON解析エラー: JSONデータが見つかりません。\n\n{raw_data}"

        data = json.loads(json_str)
        while isinstance(data, list) and len(data) == 1 and isinstance(data[0], list): 
            data = data[0]

    except json.JSONDecodeError as e:
        st.error(f"AI応答のJSON解析エラー: {e}")
        return [], f"AI応答のJSON解析に失敗しました。AIの出力形式が不正な可能性があります。\n\n---受信データ---\n{raw_data}"

    if not isinstance(data, list): 
        return [], f"AI応答データがリスト形式ではありません"

    address_map = {loc.get("地点コード"): loc.get("住所") for loc in locations if loc.get("地点コード")}
    processed_data = []

    for i, item in enumerate(data):
        if not isinstance(item, dict): 
            continue

        # 移動ステータスの場合、次の到着ステータスを探して時間範囲を生成する
        status = item.get('status', '')
        proposed_time_str = item.get('proposed_time', '')

        if status in ['移動', 'フェリー移動'] and proposed_time_str:
            start_time = proposed_time_str
            end_time = ""
            # 次の到着イベントを探す
            for next_item in data[i+1:]:
                if next_item.get('status', '') in ['到着', 'フェリー乗船', 'フェリー下船']:
                    end_time = next_item.get('proposed_time', '')
                    break

            if end_time:
                # 提案時間を「開始時間 - 終了時間」の形式に更新
                item['proposed_time'] = f"{start_time} - {end_time}"

        # データの正規化（CSV出力対応）
        processed_item = {
            "車両": str(item.get('d', 'トラック1')).strip(), 
            "提案時間": str(item.get('proposed_time', '')).strip(), 
            "希望時間": str(item.get('desired_time', '')).strip(), 
            "時間差": str(item.get('time_difference', '')).strip(), 
            "ステータス": str(item.get('status', '')).strip(), 
            "地点ID": str(item.get('location_id', '')).strip(), 
            "地点コード": str(item.get('name_code', '')).strip(), 
            "地点名": str(item.get('location_name', '')).strip(), 
            "住所": str(address_map.get(item.get('name_code', ''), '')).strip(), 
            "備考": str(item.get('remarks', '')).strip()
        }
        
        # 空のデータや重複データをスキップ
        if processed_item["車両"] and processed_item["ステータス"]:
            processed_data.append(processed_item)

    return processed_data, summary_text

def calculate_time_totals(vehicle_data):
    # 各トラックの実際の所要時間を計算（復活版）
    try:
        if len(vehicle_data) == 0:
            return "0時間0分", "0時間0分", "0時間0分"
        
        # 提案時間の最初と最後を取得
        proposed_times = []
        desired_times = []
        
        for _, row in vehicle_data.iterrows():
            if row.get('提案時間'):
                try:
                    # 時間範囲の場合（例: "2025/06/15 09:00 - 2025/06/15 11:00"）
                    proposed_time_str = str(row['提案時間'])
                    if ' - ' in proposed_time_str:
                        # 開始時間のみを取得
                        start_time_str = proposed_time_str.split(' - ')[0]
                        proposed_times.append(pd.to_datetime(start_time_str))
                    else:
                        proposed_times.append(pd.to_datetime(proposed_time_str))
                except:
                    pass
            if row.get('希望時間'):
                try:
                    desired_times.append(pd.to_datetime(row['希望時間']))
                except:
                    pass
        
        # 所要時間の計算（最早開始〜最遅終了）
        if proposed_times:
            proposed_start = min(proposed_times)
            proposed_end = max(proposed_times)
            proposed_duration = proposed_end - proposed_start
            proposed_hours = int(proposed_duration.total_seconds() // 3600)
            proposed_mins = int((proposed_duration.total_seconds() % 3600) // 60)
            proposed_total = f"{proposed_hours}時間{proposed_mins}分"
        else:
            proposed_total = "0時間0分"
            
        if desired_times:
            desired_start = min(desired_times)
            desired_end = max(desired_times)
            desired_duration = desired_end - desired_start
            desired_hours = int(desired_duration.total_seconds() // 3600)
            desired_mins = int((desired_duration.total_seconds() % 3600) // 60)
            desired_total = f"{desired_hours}時間{desired_mins}分"
        else:
            desired_total = "0時間0分"
        
        # 時間差の計算
        if proposed_times and desired_times:
            diff_seconds = (proposed_end - proposed_start).total_seconds() - (desired_end - desired_start).total_seconds()
            diff_hours = int(abs(diff_seconds) // 3600)
            diff_mins = int((abs(diff_seconds) % 3600) // 60)
            diff_sign = "+" if diff_seconds >= 0 else "-"
            time_diff = f"{diff_sign}{diff_hours}時間{diff_mins}分"
        else:
            time_diff = "0時間0分"
            
        return proposed_total, desired_total, time_diff
    except:
        return "計算中...", "計算中...", "計算中..."

def generate_map_link(vehicle_data, vehicle_name):
    # Googleマップリンクを生成（復活版）
    try:
        # 出発と到着の両方のステータスを取得
        route_points = vehicle_data[vehicle_data['ステータス'].isin(['出発', '到着'])]
        route_points = route_points.sort_values('提案時間')  # 時系列順にソート
        
        if len(route_points) == 0: 
            return
        
        addresses = [row.get('住所', '').strip() for _, row in route_points.iterrows() if row.get('住所', '').strip()]
        if not addresses: 
            return

        if len(addresses) == 1:
            url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(addresses[0])}"
        else:
            origin = urllib.parse.quote_plus(addresses[0])
            destination = urllib.parse.quote_plus(addresses[-1])
            if len(addresses) > 2:
                waypoints = '|'.join([urllib.parse.quote_plus(addr) for addr in addresses[1:-1]])
                url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination}&waypoints={waypoints}"
            else:
                url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination}"
        st.markdown(f"🗺️ [**{vehicle_name}のGoogleマップルートを開く**]({url})", unsafe_allow_html=True)
    except Exception as e:
        st.error(f"マップリンク生成エラー: {str(e)}")

def display_results(results_data, summary_text):
    # 結果表示セクション（復活版）
    if not results_data: 
        return
    st.header("📊 ルート提案")
    st.subheader("📝 AI分析サマリー")
    st.info(summary_text)
    
    df_results = pd.DataFrame(results_data)
    vehicles = df_results['車両'].unique()
    
    for vehicle in vehicles:
        with st.expander(f"🚚 {vehicle} の運行計画", expanded=True):
            vehicle_data = df_results[df_results['車両'] == vehicle]
            
            # 時間合計の計算と表示
            proposed_total, desired_total, time_diff = calculate_time_totals(vehicle_data)
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"📈 **提案時間合計**: {proposed_total}")
            with col2:
                st.markdown(f"📅 **希望時間合計**: {desired_total}")
            with col3:
                st.markdown(f"⏰ **所要時間差**: {time_diff}")
            
            st.dataframe(vehicle_data.drop('車両', axis=1), use_container_width=True, hide_index=True)
            generate_map_link(vehicle_data, vehicle)
    
    # CSV出力の修正
    try:
        # データの整理と検証
        df_export = df_results.copy()
        
        # 時間データの正規化
        df_export['提案時間'] = df_export['提案時間'].astype(str)
        df_export['希望時間'] = df_export['希望時間'].astype(str)
        df_export['時間差'] = df_export['時間差'].astype(str)
        
        # NaN値の処理
        df_export = df_export.fillna('')
        
        # 英語ヘッダーでの出力(Excel互換性向上)
        df_export.columns = [
            'Vehicle', 'Proposed_Time', 'Desired_Time', 'Time_Difference', 
            'Status', 'Location_ID', 'Location_Code', 'Location_Name', 
            'Address', 'Remarks'
        ]
        
        # CSV生成（エンコーディング修正）
        csv_buffer = io.StringIO()
        df_export.to_csv(csv_buffer, index=False, encoding='utf-8')
        csv_data = csv_buffer.getvalue()
        
        # BOM付きUTF-8で出力（Excel対応）
        csv_bytes = '\ufeff' + csv_data
        
        st.download_button(
            "📥 結果をCSVでダウンロード", 
            csv_bytes.encode('utf-8'),
            f"route_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", 
            "text/csv",
            help="ExcelやGoogleスプレッドシートで開けます"
        )
        
    except Exception as e:
        st.error(f"❌ CSV生成エラー: {str(e)}")
        st.info("💡 データを再計算してからもう一度お試しください。")
        
        # デバッグ情報（DEBUG時のみ）
        if DEBUG:
            st.error("デバッグ情報:")
            st.write("データ型:", df_results.dtypes)
            st.write("データサンプル:", df_results.head(3))
            st.write("エラー詳細:", traceback.format_exc())

def main():
    # メインアプリケーション（修正版：拠点→所属変更）
    # st.title("けっくるてぽこ - 物流サポートエージェント")
    initialize_session_state()

    with st.sidebar:
        api_ok = setup_api_keys()
        if api_ok:
            vehicle_master_section()
    
    if not st.session_state.api_initialized:
        st.warning("サイドバーでAPIキーを正しく設定してください。")
        st.stop()

    # 1画面構成：設定と結果を同一画面に表示
    selected_vehicles = vehicle_selection_section()
    st.markdown("---") 
    input_df = data_input_section()
    st.markdown("---")
    
    # 始点・終着チェック
    if input_df is not None and not input_df.empty:
        start_count = sum(1 for _, row in input_df.iterrows() if str(row.get("始点", "")).strip() == "1")
        end_count = sum(1 for _, row in input_df.iterrows() if str(row.get("終着", "")).strip() == "2")
        if start_count == 0:
            st.error("❌ 始点フラグ(1)を設定してください")
            return
        if end_count == 0:
            st.error("❌ 終着フラグ(2)を設定してください")
            return
    
    if (selected_vehicles is not None and not selected_vehicles.empty) and (input_df is not None and not input_df.empty):
        settings = optimization_settings()
        st.markdown("---")
        
        # プロンプト事前確認機能（車両選択ロジック改善版）
        with st.expander("📋 AIへの指示内容（プロンプト）を確認する", expanded=False):
            st.info("💡 ここに表示されるのは、AIへの指示の骨子です。\n実際の送信時には、これに加えて各地点間の距離と時間の詳細データが追加されます。")
            
            # 必要車両数の自動判断を表示
            min_required, conflicts = analyze_vehicle_requirements(input_df.to_dict('records'))
            if min_required > 1:
                st.warning(f"⚠️ 時間制約により最低{min_required}台の車両が必要です")
                if conflicts:
                    st.error("検出された時間重複：")
                    for conflict in conflicts:
                        st.write(f"- {conflict[0]['location']}と{conflict[1]['location']}が同時間帯に重複")
            
            preview_prompt = generate_prompt_preview(selected_vehicles.drop(columns=['選択']), st.session_state.vehicles, input_df.to_dict('records'), settings)
            st.text_area(
                label="生成されるプロンプトのプレビュー",
                value=preview_prompt,
                height=300,
                disabled=True  # 編集不可にする
            )

        col_btn1, col_btn2, col_btn3 = st.columns([1,2,1])
        with col_btn2:
            if st.button("🚀 ルート提案を実行", type="primary", use_container_width=True):
                # アクティビティ時刻を更新
                st.session_state.last_activity = datetime.now()
                
                vehicles_for_ai = selected_vehicles.drop(columns=['選択', 'メモ欄'], errors='ignore')
                try:
                    # プログレスバーで進行状況を表示
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    status_text.text("🔄 処理を開始しています...")
                    progress_bar.progress(20)
                    
                    start_time = pd.Timestamp.now()
                    results, summary, prompt = calculate_route(vehicles_for_ai, input_df.to_dict('records'), settings)
                    end_time = pd.Timestamp.now()
                    
                    progress_bar.progress(100)
                    status_text.text("✅ 処理完了！")
                    
                    st.session_state.optimization_results = {
                        "results": results, "summary": summary, "prompt": prompt,
                        "processing_time": (end_time - start_time).total_seconds()
                    }
                    st.session_state.last_activity = datetime.now()
                    
                    # プログレスバーをクリア
                    progress_bar.empty()
                    status_text.empty()
                    
                    st.success(f"✅ 提案完了！ (処理時間: {st.session_state.optimization_results['processing_time']:.1f}秒)")
                except Exception as e:
                    st.error(f"❌ エラーが発生しました: {str(e)}")
                    st.error("💡 接続エラーの場合は、ページをリロードしてください。")
                    if DEBUG: 
                        st.error(traceback.format_exc())
        
        # 1画面構成：結果を同一画面内に表示
        if "optimization_results" in st.session_state and st.session_state.optimization_results:
            st.markdown("---")
            display_results(st.session_state.optimization_results["results"], st.session_state.optimization_results["summary"])
            
            with st.expander("🔍 実際にAIに送信したプロンプトを確認する"):
                st.text_area("送信済みプロンプト", value=st.session_state.optimization_results["prompt"], height=300, key="debug_prompt_display")
            
            # 新しい計画ボタン
            col_reset1, col_reset2, col_reset3 = st.columns([1,2,1])
            with col_reset2:
                if st.button("🔄 条件を変更して再計算", use_container_width=True):
                    st.session_state.optimization_results = None
                    st.rerun()
    else:
        st.info("👆 ステップ1とステップ2で、車両と配送先データを入力してください。")

if __name__ == "__main__":
    main()