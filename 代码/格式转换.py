import re
import os

# ---------- 全局常量 ----------
# 九位常驻角色名单
PERMANENT_ROLES = [
    '顾子尧', '夏予扬', '乔殊', '林致',
    '柏闻', '季少一', '江恪', '许向安', '许向宁'
]

# 角色别名映射（用于高频重复检测）
ALIAS_MAP = {
    '季少', '殊殊子', '吱吱', '顾饺', '宁宁', '安安', '柏队', '克制哥'
}
# 所有需要高频过滤的词汇（正式名 + 别名 + 团名）
FILTER_NAMES = set(PERMANENT_ROLES) | ALIAS_MAP | {'LASER', 'MANTA'}

# 垃圾信息关键词（命中任一即整行删除）
FILTER_KEYWORDS = ['字幕', '字幕君', '字幕组', '野生', '毒唯']

# ---------- 预处理：时间轴清洗 ----------
TIME_PATTERN = re.compile(
    r'^[\[【]?'
    r'('
    r'\d{2}:\d{2}:\d{2}(?:\.\d+)?'            # HH:MM:SS.ms
    r'|'
    r'\d{2}:\d{2}(?:\.\d+)?'                  # MM:SS.ms
    r')'
    r'[\]】]?\s*[-—~]?\s*',                     # 可选的中括号、横线等
    re.UNICODE
)

def remove_timestamp(line: str) -> str:
    """移除行首时间戳标记，返回剩余文本"""
    return TIME_PATTERN.sub('', line).lstrip()

# ---------- 文本清洗辅助函数 ----------
def clean_for_duplicate_check(text: str) -> str:
    """移除所有空格和标点，用于纯团名/纯感叹刷屏检测"""
    # 只保留汉字、字母、数字，其余删除
    return re.sub(r'[^\w\u4e00-\u9fff]', '', text, flags=re.UNICODE)

def is_garbage_line(line: str) -> bool:
    """
    垃圾信息过滤（满足任一条件返回 True，整行丢弃）
    1. 包含关键词
    2. 清洗后仅为 LASER 或 MANTA（不区分大小写）
    3. 清洗后为同一字符重复 >=4 次
    4. 角色名/别名/团名出现 >=3 次
    """
    # 条件1：关键词过滤
    for kw in FILTER_KEYWORDS:
        if kw in line:
            return True

    cleaned = clean_for_duplicate_check(line)
    cleaned_lower = cleaned.lower()

    # 条件2：纯团名
    if cleaned_lower in ('laser', 'manta'):
        return True

    # 条件3：纯感叹刷屏（同一字符重复4次及以上）
    if len(cleaned) >= 4 and len(set(cleaned)) == 1:
        return True

    # 条件4：高频重复（不区分大小写计数）
    line_lower = line.lower()
    for name in FILTER_NAMES:
        # 统计该名称在行内出现的次数
        count = line_lower.count(name.lower())
        if count >= 3:
            return True

    return False

# ---------- 环境描写与角色台词解析 ----------
SCENE_PATTERN = re.compile(r'^【(.*)】$')          # 【内容】
ROLE_LINE_PATTERN = re.compile(r'^([^：:]+)[：:]\s*(.*)$')  # 角色名：台词

def parse_line(line: str):
    """
    将清洗后的行解析为结构化数据：
    - 环境描写返回 ('env', content)
    - 角色台词返回 ('dialogue', role, speech)
    - 普通文本返回 ('plain', text)
    若无法识别则返回 None
    """
    # 1. 环境描写检测：以【开头，】结尾，且内容不包含常驻角色名前缀
    scene_match = SCENE_PATTERN.match(line)
    if scene_match:
        content = scene_match.group(1)
        # 检查内容是否以常驻角色名开头（例如【顾子尧】不会被当成环境描写）
        if not any(content.startswith(role) for role in PERMANENT_ROLES):
            return ('env', content)

    # 2. 角色台词检测（角色名：台词）
    role_match = ROLE_LINE_PATTERN.match(line)
    if role_match:
        role = role_match.group(1).strip()
        speech = role_match.group(2).strip()
        # 即使角色不在常驻名单，也统一转换为【角色名】格式（满足“非常驻也要方括号”要求）
        return ('dialogue', role, speech)

    # 3. 其他（可能是旁白、动作说明等）作为普通台词处理
    if line:
        return ('plain', line)

    return None

# ---------- 格式化输出 ----------
def format_entry(entry) -> list:
    """将结构化条目转换为输出行列表（可能为1行或2行）"""
    if entry['type'] == 'env':
        return [f'（{entry["content"]}）']
    elif entry['type'] == 'dialogue':
        lines = [f'【{entry["role"]}】']
        if entry['speech']:
            lines.append(f'    {entry["speech"]}')
        return lines
    elif entry['type'] == 'plain':
        # 普通台词缩进4空格
        return [f'    {entry["text"]}']
    return []

# ---------- 主格式化函数（集成去重） ----------
def format_script(text: str) -> str:
    # 第一步：按行分割，去除首尾空白，丢弃空行
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]

    # 第二步：时间轴清洗 + 垃圾过滤 + 解析为结构化条目
    entries = []
    for line in raw_lines:
        # 去除时间戳
        cleaned = remove_timestamp(line)
        if not cleaned:
            continue
        # 垃圾过滤
        if is_garbage_line(cleaned):
            continue
        # 解析类型
        parsed = parse_line(cleaned)
        if parsed is None:
            continue

        if parsed[0] == 'env':
            entries.append({'type': 'env', 'content': parsed[1]})
        elif parsed[0] == 'dialogue':
            entries.append({'type': 'dialogue', 'role': parsed[1], 'speech': parsed[2]})
        elif parsed[0] == 'plain':
            entries.append({'type': 'plain', 'text': parsed[1]})

    # 第三步：去重 —— 完全相同的台词（仅针对dialogue和plain的文本内容）只保留第一次出现
    seen_speeches = set()
    unique_entries = []
    for entry in entries:
        if entry['type'] == 'dialogue':
            speech = entry['speech']
            if speech in seen_speeches:
                continue  # 重复台词，整条丢弃
            seen_speeches.add(speech)
            unique_entries.append(entry)
        elif entry['type'] == 'plain':
            text = entry['text']
            if text in seen_speeches:
                continue
            seen_speeches.add(text)
            unique_entries.append(entry)
        else:
            # 环境描写不去重，直接保留
            unique_entries.append(entry)

    # 第四步：格式化输出行
    output_lines = []
    for entry in unique_entries:
        output_lines.extend(format_entry(entry))

    return '\n'.join(output_lines)

# ---------- 批量处理函数（保持不变） ----------
def process_all_subfolders(root_input_folder, root_output_folder):
    """
    批量处理【总文件夹】下的【所有子文件夹】
    保持原有文件夹结构，全部格式化
    """
    if not os.path.exists(root_output_folder):
        os.makedirs(root_output_folder)

    for foldername in os.listdir(root_input_folder):
        input_subfolder = os.path.join(root_input_folder, foldername)
        if not os.path.isdir(input_subfolder):
            continue

        output_subfolder = os.path.join(root_output_folder, foldername)
        if not os.path.exists(output_subfolder):
            os.makedirs(output_subfolder)

        print(f"\n📂 正在处理文件夹：{foldername}")

        for filename in os.listdir(input_subfolder):
            if filename.lower().endswith('.txt'):
                input_path = os.path.join(input_subfolder, filename)
                output_path = os.path.join(output_subfolder, filename)

                try:
                    with open(input_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    formatted = format_script(content)

                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(formatted)

                    print(f"✅ {filename}")

                except Exception as e:
                    print(f"❌ {filename} 失败：{str(e)}")

# ---------- 配置与入口 ----------
INPUT_FOLDER = r"C:\Users\ThinkPad\Desktop\杂\逐声计划\团综文字整理\自动生成字幕_总输出"
OUTPUT_FOLDER = r"C:\Users\ThinkPad\Desktop\杂\逐声计划\团综文字整理\规范剧本_最终版"

if __name__ == '__main__':
    print("=" * 60)
    print("        🔥 全文件夹剧本格式化工具（增强版）🔥")
    print("  自动遍历所有子文件夹 → 保持结构 → 规范输出")
    print("  新增：时间轴全面清洗 · 垃圾过滤 · 台词去重")
    print("=" * 60)

    process_all_subfolders(INPUT_FOLDER, OUTPUT_FOLDER)

    print("\n🎉🎉🎉 全部处理完成！")
    print(f"📂 规范剧本已保存到：\n{OUTPUT_FOLDER}")