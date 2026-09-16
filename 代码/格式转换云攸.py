import re
import os
import csv

# ====================== 请修改为您的真实路径 ======================
INPUT_ROOT = r"C:\Users\ThinkPad\Desktop\杂\逐声计划\团综文字整理\字幕整理\未格式化\云攸爬虫"
OUTPUT_ROOT = r"C:\Users\ThinkPad\Desktop\杂\逐声计划\团综文字整理\字幕整理\已格式化_云攸爬虫"
ROLES_DIR = r"C:\Users\ThinkPad\Desktop\杂\逐声计划\团综文字整理\代码\自动获取弹幕\剧集信息"
# ================================================================

# ----- 常驻角色（固定）-----
CORE_ROLES = {
    "顾子尧", "夏予扬", "乔殊", "林致",
    "柏闻", "季少一", "江恪", "许向安", "许向宁"
}
# ----- 别名（仅用于垃圾检测，不影响角色判断）-----
ALIAS_NAMES = {
    "季少", "殊殊子", "吱吱", "顾饺", "宁宁", "安安", "柏队", "克制哥",
    "LASER", "MANTA"
}

# ----- 从CSV加载非常驻角色 -----
def load_temporary_roles(directory):
    temp = set()
    if not os.path.exists(directory):
        print(f"⚠️ 角色表目录不存在：{directory}")
        return temp
    for fname in os.listdir(directory):
        if not fname.lower().endswith('.csv'):
            continue
        path = os.path.join(directory, fname)
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    chars = row.get('temporary_chars', '').strip()
                    if not chars or chars == '没有':
                        continue
                    for name in chars.split():
                        name = name.strip()
                        if name and name != '没有':
                            temp.add(name)
        except Exception as e:
            print(f"⚠️ 读取CSV失败 {path}: {e}")
    return temp

print("正在加载非常驻角色...")
TEMPORARY_ROLES = load_temporary_roles(ROLES_DIR)
print(f"✅ 非常驻角色：{', '.join(sorted(TEMPORARY_ROLES)) if TEMPORARY_ROLES else '无'}")

# 所有角色名（常驻+非常驻）用于判断【】是否为角色
ALL_ROLES = CORE_ROLES | TEMPORARY_ROLES

# ----- 垃圾过滤关键词（保持不变）-----
JUNK_KEYWORDS = {"字幕", "字幕君", "字幕组", "野生", "毒唯"}

def remove_timestamps(line: str) -> str:
    # 删除行首时间戳
    pattern = re.compile(r'^\[?\d{1,2}[:：.]\d{1,2}(?:[:：.]\d{1,3})?\]?\s*')
    cleaned = pattern.sub('', line).strip()
    if cleaned and cleaned[0].isdigit():
        time_like = re.match(r'^\d{1,2}[:：]\d{1,2}(?:[:：]\d{1,2})?\s*', cleaned)
        if time_like:
            cleaned = cleaned[time_like.end():].strip()
    return cleaned

def has_english_brackets(line: str) -> bool:
    return '[' in line or ']' in line

def is_pure_team_name(line: str) -> bool:
    cleaned = re.sub(r'[^\w]', '', line, flags=re.UNICODE)
    return cleaned.upper() in ("LASER", "MANTA")

def is_repetitive_exclamation(line: str) -> bool:
    if len(line) < 4:
        return False
    return all(ch == line[0] for ch in line)

def has_high_freq_name(line: str) -> bool:
    # 高频重复检测（使用所有角色名+别名）
    all_names = ALL_ROLES | ALIAS_NAMES
    line_low = line.lower()
    count = 0
    for name in all_names:
        count += line_low.count(name.lower())
        if count >= 3:
            return True
    return False

def is_junk_line(line: str) -> bool:
    if not line.strip():
        return True
    if has_english_brackets(line):
        return True
    if any(kw in line for kw in JUNK_KEYWORDS):
        return True
    if is_pure_team_name(line):
        return True
    if is_repetitive_exclamation(line):
        return True
    if has_high_freq_name(line):
        return True
    return False

def format_script(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    output = []
    seen = set()

    for raw_line in lines:
        # 1. 删时间轴
        line = remove_timestamps(raw_line)
        if not line:
            continue
        # 2. 垃圾行过滤
        if is_junk_line(line):
            continue

        # 3. 处理角色行（带冒号或【】的）
        # 先尝试匹配 角色名：台词 或 角色名:台词
        colon_match = re.match(r'^([^：:]+)[：:]\s*(.*)$', line)
        if colon_match:
            name = colon_match.group(1).strip()
            speech = colon_match.group(2).strip()
            dedup_key = f"ROLE|{name}|{speech}"
            if dedup_key not in seen:
                seen.add(dedup_key)
                output.append(f"【{name}】")
                if speech:
                    output.append(f"    {speech}")
            continue

        # 再匹配 【xxx】... 格式（可能后面有台词）
        bracket_match = re.match(r'^【(.+?)】\s*(.*)$', line)
        if bracket_match:
            content = bracket_match.group(1).strip()
            rest = bracket_match.group(2).strip()
            # 核心判断：如果 content 是角色名（常驻/非常驻），则保留【】作为角色标记
            if content in ALL_ROLES:
                # 角色行
                dedup_key = f"ROLE|{content}|{rest}"
                if dedup_key not in seen:
                    seen.add(dedup_key)
                    output.append(f"【{content}】")
                    if rest:
                        output.append(f"    {rest}")
            else:
                # 不是角色名 → 环境描写，将【】改为（）
                scene_text = f"（{content}）"
                if rest:
                    # 如果【】后面还有文字，那说明不是纯环境描写，可能是误写，按普通文本缩进处理
                    scene_text = f"（{content}）{rest}"
                dedup_key = f"SCENE|{scene_text}"
                if dedup_key not in seen:
                    seen.add(dedup_key)
                    output.append(f"    {scene_text}")  # 环境描写顶格？用户要求“改成括号”，没有明确缩进，按一般理解环境描写顶格
                    # 但之前要求环境描写顶格无缩进，这里修正：
                    # 实际上应该是顶格，但上面写了缩进，我重新调整：环境描写顶格
            continue

        # 4. 普通文本（无冒号也无【】）
        dedup_key = f"TEXT|{line}"
        if dedup_key not in seen:
            seen.add(dedup_key)
            output.append(f"    {line}")

    # 修正环境描写的缩进：将上面错误加的空格去掉（统一顶格）
    final_output = []
    for line in output:
        if line.startswith('（') and not line.startswith('    （'):
            # 已经是顶格
            final_output.append(line)
        elif line.startswith('    （'):
            # 去掉前导空格
            final_output.append(line.lstrip())
        else:
            final_output.append(line)
    return '\n'.join(final_output)

def process_folder_tree(input_root, output_root):
    if not os.path.exists(input_root):
        print(f"❌ 输入文件夹不存在：{input_root}")
        return
    total = 0
    processed = 0
    for root, dirs, files in os.walk(input_root):
        rel = os.path.relpath(root, input_root)
        target = os.path.join(output_root, rel)
        os.makedirs(target, exist_ok=True)
        for f in files:
            if f.lower().endswith('.txt'):
                total += 1
                in_path = os.path.join(root, f)
                out_path = os.path.join(target, f)
                try:
                    with open(in_path, 'r', encoding='utf-8') as fp:
                        content = fp.read()
                    formatted = format_script(content)
                    with open(out_path, 'w', encoding='utf-8') as fp:
                        fp.write(formatted)
                    print(f"✅ {in_path} -> {len(formatted.splitlines())} 行")
                    processed += 1
                except Exception as e:
                    print(f"❌ {in_path}: {e}")
    print(f"\n📊 共 {total} 个txt，成功 {processed} 个")
    print(f"📂 输出目录：{os.path.abspath(output_root)}")

if __name__ == '__main__':
    print("=" * 60)
    print("  逐声计划 字幕格式化工具 v6.0")
    print("  核心规则：【内容】是角色→保留【】；不是角色→改为（）")
    print("=" * 60)
    process_folder_tree(INPUT_ROOT, OUTPUT_ROOT)
    print("\n🎉 完成！")