#!/usr/bin/env python3
"""
P0.24 易经认知编码系统 - Phase 1 数据构建脚本
从《说卦传》+ 64卦速查表 + 用户个人笔记 构建三层JSON数据
"""
import json
import os

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# 1. trigram_table.json — 八卦取象编码表（来源：《说卦传》全文11章）
# ============================================================

trigrams = {
    "qian": {
        "name": "乾", "symbol": "☰", "pinyin": "qián",
        "binary": "111", "binary_value": 7,
        "nature": "天", "attribute": "健",
        "element": "金", "direction": "西北",
        "season": "秋冬之交",
        "xiantian_number": 1,
        "family_role": "父",
        "animal": "马", "body_part": "首",
        "chapter_4_role": "乾以君之",
        "chapter_5_role": "战乎乾（阴阳相薄）",
        "wanwu_leixiang": [
            "天", "圜", "君", "父", "玉", "金", "寒", "冰", "大赤",
            "良马", "瘠马", "驳马", "木果"
        ],
        "chapter": "说卦传第十一章",
        "source": "说卦传"
    },
    "kun": {
        "name": "坤", "symbol": "☷", "pinyin": "kūn",
        "binary": "000", "binary_value": 0,
        "nature": "地", "attribute": "顺",
        "element": "土", "direction": "西南",
        "season": "夏秋之交",
        "xiantian_number": 8,
        "family_role": "母",
        "animal": "牛", "body_part": "腹",
        "chapter_4_role": "坤以藏之",
        "chapter_5_role": "致役乎坤（万物皆致养焉）",
        "wanwu_leixiang": [
            "地", "母", "布", "釜", "吝啬", "均", "子母牛", "大舆",
            "文", "众", "柄", "黑（地色）"
        ],
        "chapter": "说卦传第十一章",
        "source": "说卦传"
    },
    "zhen": {
        "name": "震", "symbol": "☳", "pinyin": "zhèn",
        "binary": "001", "binary_value": 1,
        "nature": "雷", "attribute": "动",
        "element": "木", "direction": "东",
        "season": "春",
        "xiantian_number": 4,
        "family_role": "长男",
        "animal": "龙", "body_part": "足",
        "chapter_4_role": "雷以动之",
        "chapter_5_role": "帝出乎震（万物出乎震）",
        "wanwu_leixiang": [
            "雷", "龙", "玄黄", "敷", "大涂", "长子", "决躁",
            "苍莨竹", "萑苇", "善鸣马", "的颡马", "反生稼",
            "健（其究）", "蕃鲜（其究）"
        ],
        "chapter": "说卦传第十一章",
        "source": "说卦传"
    },
    "xun": {
        "name": "巽", "symbol": "☴", "pinyin": "xùn",
        "binary": "110", "binary_value": 6,
        "nature": "风", "attribute": "入",
        "element": "木", "direction": "东南",
        "season": "春夏之交",
        "xiantian_number": 5,
        "family_role": "长女",
        "animal": "鸡", "body_part": "股",
        "chapter_4_role": "风以散之",
        "chapter_5_role": "齐乎巽（万物之洁齐）",
        "wanwu_leixiang": [
            "木", "风", "长女", "绳直", "工", "白", "长", "高",
            "进退", "不果", "臭",
            "寡发人", "广颡人", "多白眼人", "近利市三倍",
            "躁卦（其究）"
        ],
        "chapter": "说卦传第十一章",
        "source": "说卦传"
    },
    "kan": {
        "name": "坎", "symbol": "☵", "pinyin": "kǎn",
        "binary": "010", "binary_value": 2,
        "nature": "水", "attribute": "陷",
        "element": "水", "direction": "北",
        "season": "冬",
        "xiantian_number": 6,
        "family_role": "中男",
        "animal": "豕", "body_part": "耳",
        "chapter_4_role": "雨以润之",
        "chapter_5_role": "劳乎坎（万物之所归）",
        "wanwu_leixiang": [
            "水", "沟渎", "隐伏", "矫輮", "弓轮",
            "加忧人", "心病人", "耳痛人", "血卦", "赤",
            "美脊马", "亟心马", "下首马", "薄蹄马", "曳马",
            "丁躜舆", "通", "月", "盗", "坚多心木"
        ],
        "chapter": "说卦传第十一章",
        "source": "说卦传"
    },
    "li": {
        "name": "离", "symbol": "☲", "pinyin": "lí",
        "binary": "101", "binary_value": 5,
        "nature": "火", "attribute": "丽",
        "element": "火", "direction": "南",
        "season": "夏",
        "xiantian_number": 3,
        "family_role": "中女",
        "animal": "雉", "body_part": "目",
        "chapter_4_role": "日以晅之",
        "chapter_5_role": "相见乎离（万物皆相见）",
        "wanwu_leixiang": [
            "火", "日", "电", "中女", "甲胄", "戈兵",
            "大腹人", "乾卦",
            "鳖", "蟹", "蠃", "蚌", "龟", "科上槁木"
        ],
        "chapter": "说卦传第十一章",
        "source": "说卦传"
    },
    "gen": {
        "name": "艮", "symbol": "☶", "pinyin": "gèn",
        "binary": "100", "binary_value": 4,
        "nature": "山", "attribute": "止",
        "element": "土", "direction": "东北",
        "season": "冬春之交",
        "xiantian_number": 7,
        "family_role": "少男",
        "animal": "狗", "body_part": "手",
        "chapter_4_role": "艮以止之",
        "chapter_5_role": "成言乎艮（万物之所成，终而所成始）",
        "wanwu_leixiang": [
            "山", "径路", "小石", "门阙", "果蓏", "阍寺",
            "指", "狗", "鼠", "黔喙之属", "坚多节木"
        ],
        "chapter": "说卦传第十一章",
        "source": "说卦传"
    },
    "dui": {
        "name": "兑", "symbol": "☱", "pinyin": "duì",
        "binary": "011", "binary_value": 3,
        "nature": "泽", "attribute": "说（悦）",
        "element": "金", "direction": "西",
        "season": "秋",
        "xiantian_number": 2,
        "family_role": "少女",
        "animal": "羊", "body_part": "口",
        "chapter_4_role": "兑以说之",
        "chapter_5_role": "说言乎兑（万物之所说）",
        "wanwu_leixiang": [
            "泽", "少女", "巫", "口舌", "毁折", "附决",
            "刚卤地", "妾", "羊"
        ],
        "chapter": "说卦传第十一章",
        "source": "说卦传"
    }
}

# 五行生克关系
wuxing_relations = {
    "相生": ["金生水", "水生木", "木生火", "火生土", "土生金"],
    "相克": ["金克木", "木克土", "土克水", "水克火", "火克金"]
}

# 十二消息卦（Layer 6 振荡基线层）
twelve_messages = [
    {"name": "复", "yang_count": 1, "month": 11, "season": "冬至", "hexagram": "地雷复", "psi_baseline": -0.8},
    {"name": "临", "yang_count": 2, "month": 12, "season": "大寒", "hexagram": "地泽临", "psi_baseline": -0.6},
    {"name": "泰", "yang_count": 3, "month": 1, "season": "立春", "hexagram": "地天泰", "psi_baseline": -0.3},
    {"name": "大壮", "yang_count": 4, "month": 2, "season": "春分", "hexagram": "雷天大壮", "psi_baseline": 0.0},
    {"name": "夬", "yang_count": 5, "month": 3, "season": "谷雨", "hexagram": "泽天夬", "psi_baseline": 0.3},
    {"name": "乾", "yang_count": 6, "month": 4, "season": "小满", "hexagram": "乾为天", "psi_baseline": 0.5},
    {"name": "姤", "yang_count": 5, "month": 5, "season": "夏至", "hexagram": "天风姤", "psi_baseline": 0.3},
    {"name": "遁", "yang_count": 4, "month": 6, "season": "大暑", "hexagram": "天山遁", "psi_baseline": 0.0},
    {"name": "否", "yang_count": 3, "month": 7, "season": "立秋", "hexagram": "天地否", "psi_baseline": -0.3},
    {"name": "观", "yang_count": 2, "month": 8, "season": "秋分", "hexagram": "风地观", "psi_baseline": -0.6},
    {"name": "剥", "yang_count": 1, "month": 9, "season": "霜降", "hexagram": "山地剥", "psi_baseline": -0.8},
    {"name": "坤", "yang_count": 0, "month": 10, "season": "小雪", "hexagram": "坤为地", "psi_baseline": -1.0}
]

trigram_data = {
    "meta": {
        "version": "1.0",
        "description": "八卦取象编码表 — 来源：《说卦传》全文11章",
        "source": "说卦传（周易·易传）",
        "source_url": "https://www.wenxue360.com/zhouyi/archives/82.html",
        "created": "2026-08-03",
        "notes": "8个抽象属性（健顺动入陷丽止悦）构成开放分类系统，取象基于功能属性而非具体事物"
    },
    "trigrams": trigrams,
    "wuxing_relations": wuxing_relations,
    "twelve_message_hexagrams": twelve_messages,
    "attribute_system": {
        "description": "《说卦传》第七章定义的8个核心功能属性",
        "attributes": {
            "健": "乾 — 刚健不息，天道运行",
            "顺": "坤 — 柔顺承载，地道滋养",
            "动": "震 — 震动激发，雷声唤万物",
            "入": "巽 — 渗入无孔不入，风行天下",
            "陷": "坎 — 陷落险阻，水流就低",
            "丽": "离 — 附丽光明，火附于物而明",
            "止": "艮 — 静止稳固，山岳安止",
            "说": "兑 — 喜悦和说，泽润万物"
        },
        "open_classification": True,
        "classification_note": "同一对象从不同角度可归入不同卦（保温瓶例：盖着=乾圆刚/打开=兑上缺/中空=震中虚/倒置=艮上实下空）"
    }
}

# ============================================================
# 2. hexagram_strategies_base.json — 64卦策略基础层
#    来源：天机爻Wiki 64卦速查表 + 详细解读（8卦完整）+ 卦辞（64卦完整）
# ============================================================

# 64卦基础数据（从天机爻Wiki速查表提取，全部64卦）
hexagrams_base = [
    {"num":1,"name":"乾为天","symbol":"䷀","upper":"乾","lower":"乾","palace":"乾宫","gua_ci":"元亨利贞","binary":"111111"},
    {"num":2,"name":"坤为地","symbol":"䷁","upper":"坤","lower":"坤","palace":"坤宫","gua_ci":"元亨，利牝马之贞","binary":"000000"},
    {"num":3,"name":"水雷屯","symbol":"䷂","upper":"坎","lower":"震","palace":"坎宫","gua_ci":"元亨利贞，勿用有攸往","binary":"100010"},
    {"num":4,"name":"山水蒙","symbol":"䷃","upper":"艮","lower":"坎","palace":"离宫","gua_ci":"亨。匪我求童蒙，童蒙求我","binary":"010001"},
    {"num":5,"name":"水天需","symbol":"䷄","upper":"坎","lower":"乾","palace":"坤宫","gua_ci":"有孚，光亨，贞吉","binary":"010111"},
    {"num":6,"name":"天水讼","symbol":"䷅","upper":"乾","lower":"坎","palace":"离宫","gua_ci":"有孚窒惕，中吉，终凶","binary":"111010"},
    {"num":7,"name":"地水师","symbol":"䷆","upper":"坤","lower":"坎","palace":"坎宫","gua_ci":"贞，丈人吉，无咎","binary":"000010"},
    {"num":8,"name":"水地比","symbol":"䷇","upper":"坎","lower":"坤","palace":"坤宫","gua_ci":"吉，原筮，元永贞，无咎","binary":"010000"},
    {"num":9,"name":"风天小畜","symbol":"䷈","upper":"巽","lower":"乾","palace":"巽宫","gua_ci":"亨。密云不雨，自我西郊","binary":"110111"},
    {"num":10,"name":"天泽履","symbol":"䷉","upper":"乾","lower":"兑","palace":"艮宫","gua_ci":"履虎尾，不咥人，亨","binary":"111011"},
    {"num":11,"name":"地天泰","symbol":"䷊","upper":"坤","lower":"乾","palace":"坤宫","gua_ci":"小往大来，吉亨","binary":"000111"},
    {"num":12,"name":"天地否","symbol":"䷋","upper":"乾","lower":"坤","palace":"乾宫","gua_ci":"否之匪人，不利君子贞","binary":"111000"},
    {"num":13,"name":"天火同人","symbol":"䷌","upper":"乾","lower":"离","palace":"离宫","gua_ci":"同人于野，亨","binary":"111101"},
    {"num":14,"name":"火天大有","symbol":"䷍","upper":"离","lower":"乾","palace":"乾宫","gua_ci":"元亨","binary":"101111"},
    {"num":15,"name":"地山谦","symbol":"䷎","upper":"坤","lower":"艮","palace":"兑宫","gua_ci":"亨，君子有终","binary":"000100"},
    {"num":16,"name":"雷地豫","symbol":"䷏","upper":"震","lower":"坤","palace":"震宫","gua_ci":"利建侯行师","binary":"001000"},
    {"num":17,"name":"泽雷随","symbol":"䷐","upper":"兑","lower":"震","palace":"震宫","gua_ci":"元亨利贞，无咎","binary":"011001"},
    {"num":18,"name":"山风蛊","symbol":"䷑","upper":"艮","lower":"巽","palace":"巽宫","gua_ci":"元亨，利涉大川","binary":"100110"},
    {"num":19,"name":"地泽临","symbol":"䷒","upper":"坤","lower":"兑","palace":"坤宫","gua_ci":"元亨利贞，至于八月有凶","binary":"000011"},
    {"num":20,"name":"风地观","symbol":"䷓","upper":"巽","lower":"坤","palace":"乾宫","gua_ci":"盥而不荐，有孚颙若","binary":"110000"},
    {"num":21,"name":"火雷噬嗑","symbol":"䷔","upper":"离","lower":"震","palace":"巽宫","gua_ci":"亨，利用狱","binary":"101001"},
    {"num":22,"name":"山火贲","symbol":"䷕","upper":"艮","lower":"离","palace":"艮宫","gua_ci":"亨，小利有攸往","binary":"100101"},
    {"num":23,"name":"山地剥","symbol":"䷖","upper":"艮","lower":"坤","palace":"乾宫","gua_ci":"不利有攸往","binary":"100000"},
    {"num":24,"name":"地雷复","symbol":"䷗","upper":"坤","lower":"震","palace":"坤宫","gua_ci":"亨，出入无疾","binary":"000001"},
    {"num":25,"name":"天雷无妄","symbol":"䷘","upper":"乾","lower":"震","palace":"巽宫","gua_ci":"元亨利贞，其匪正有眚","binary":"111001"},
    {"num":26,"name":"山天大畜","symbol":"䷙","upper":"艮","lower":"乾","palace":"艮宫","gua_ci":"利贞，不家食吉","binary":"100111"},
    {"num":27,"name":"山雷颐","symbol":"䷚","upper":"艮","lower":"震","palace":"巽宫","gua_ci":"贞吉，观颐，自求口实","binary":"100001"},
    {"num":28,"name":"泽风大过","symbol":"䷛","upper":"兑","lower":"巽","palace":"震宫","gua_ci":"栋桡，利有攸往，亨","binary":"011110"},
    {"num":29,"name":"坎为水","symbol":"䷜","upper":"坎","lower":"坎","palace":"坎宫","gua_ci":"习坎，有孚，维心亨","binary":"010010"},
    {"num":30,"name":"离为火","symbol":"䷝","upper":"离","lower":"离","palace":"离宫","gua_ci":"利贞，亨，畜牝牛吉","binary":"101101"},
    {"num":31,"name":"泽山咸","symbol":"䷞","upper":"兑","lower":"艮","palace":"兑宫","gua_ci":"亨，利贞，取女吉","binary":"011100"},
    {"num":32,"name":"雷风恒","symbol":"䷟","upper":"震","lower":"巽","palace":"震宫","gua_ci":"亨，无咎，利贞","binary":"001110"},
    {"num":33,"name":"天山遁","symbol":"䷠","upper":"乾","lower":"艮","palace":"乾宫","gua_ci":"亨，小利贞","binary":"111100"},
    {"num":34,"name":"雷天大壮","symbol":"䷡","upper":"震","lower":"乾","palace":"坤宫","gua_ci":"利贞","binary":"001111"},
    {"num":35,"name":"火地晋","symbol":"䷢","upper":"离","lower":"坤","palace":"乾宫","gua_ci":"康侯用锡马蕃庶，昼日三接","binary":"101000"},
    {"num":36,"name":"地火明夷","symbol":"䷣","upper":"坤","lower":"离","palace":"坎宫","gua_ci":"利艰贞","binary":"000101"},
    {"num":37,"name":"风火家人","symbol":"䷤","upper":"巽","lower":"离","palace":"巽宫","gua_ci":"利女贞","binary":"110101"},
    {"num":38,"name":"火泽睽","symbol":"䷥","upper":"离","lower":"兑","palace":"艮宫","gua_ci":"小事吉","binary":"101011"},
    {"num":39,"name":"水山蹇","symbol":"䷦","upper":"坎","lower":"艮","palace":"兑宫","gua_ci":"利西南，不利东北","binary":"010100"},
    {"num":40,"name":"雷水解","symbol":"䷧","upper":"震","lower":"坎","palace":"震宫","gua_ci":"利西南，无所往，其来复吉","binary":"001010"},
    {"num":41,"name":"山泽损","symbol":"䷨","upper":"艮","lower":"兑","palace":"艮宫","gua_ci":"有孚，元吉，无咎","binary":"100011"},
    {"num":42,"name":"风雷益","symbol":"䷩","upper":"巽","lower":"震","palace":"巽宫","gua_ci":"利有攸往，利涉大川","binary":"110001"},
    {"num":43,"name":"泽天夬","symbol":"䷪","upper":"兑","lower":"乾","palace":"坤宫","gua_ci":"扬于王庭，孚号有厉","binary":"011111"},
    {"num":44,"name":"天风姤","symbol":"䷫","upper":"乾","lower":"巽","palace":"乾宫","gua_ci":"女壮，勿用取女","binary":"111110"},
    {"num":45,"name":"泽地萃","symbol":"䷬","upper":"兑","lower":"坤","palace":"兑宫","gua_ci":"亨，王假有庙","binary":"011000"},
    {"num":46,"name":"地风升","symbol":"䷭","upper":"坤","lower":"巽","palace":"震宫","gua_ci":"元亨，用见大人","binary":"000110"},
    {"num":47,"name":"泽水困","symbol":"䷮","upper":"兑","lower":"坎","palace":"兑宫","gua_ci":"亨，贞，大人吉","binary":"011010"},
    {"num":48,"name":"水风井","symbol":"䷯","upper":"坎","lower":"巽","palace":"震宫","gua_ci":"改邑不改井，无丧无得","binary":"010110"},
    {"num":49,"name":"泽火革","symbol":"䷰","upper":"兑","lower":"离","palace":"坎宫","gua_ci":"己日乃孚，元亨利贞","binary":"011101"},
    {"num":50,"name":"火风鼎","symbol":"䷱","upper":"离","lower":"巽","palace":"离宫","gua_ci":"元吉，亨","binary":"101110"},
    {"num":51,"name":"震为雷","symbol":"䷲","upper":"震","lower":"震","palace":"震宫","gua_ci":"亨，震来虩虩，笑言哑哑","binary":"001001"},
    {"num":52,"name":"艮为山","symbol":"䷳","upper":"艮","lower":"艮","palace":"艮宫","gua_ci":"艮其背，不获其身","binary":"100100"},
    {"num":53,"name":"风山渐","symbol":"䷴","upper":"巽","lower":"艮","palace":"艮宫","gua_ci":"女归吉，利贞","binary":"110100"},
    {"num":54,"name":"雷泽归妹","symbol":"䷵","upper":"震","lower":"兑","palace":"兑宫","gua_ci":"征凶，无攸利","binary":"001011"},
    {"num":55,"name":"雷火丰","symbol":"䷶","upper":"震","lower":"离","palace":"坎宫","gua_ci":"亨，王假之，勿忧","binary":"001101"},
    {"num":56,"name":"火山旅","symbol":"䷷","upper":"离","lower":"艮","palace":"离宫","gua_ci":"小亨，旅贞吉","binary":"101100"},
    {"num":57,"name":"巽为风","symbol":"䷸","upper":"巽","lower":"巽","palace":"巽宫","gua_ci":"小亨，利有攸往，利见大人","binary":"110110"},
    {"num":58,"name":"兑为泽","symbol":"䷹","upper":"兑","lower":"兑","palace":"兑宫","gua_ci":"亨，利贞","binary":"011011"},
    {"num":59,"name":"风水涣","symbol":"䷺","upper":"巽","lower":"坎","palace":"离宫","gua_ci":"亨，王假有庙，利涉大川","binary":"110010"},
    {"num":60,"name":"水泽节","symbol":"䷻","upper":"坎","lower":"兑","palace":"坎宫","gua_ci":"亨，苦节不可贞","binary":"010011"},
    {"num":61,"name":"风泽中孚","symbol":"䷼","upper":"巽","lower":"兑","palace":"艮宫","gua_ci":"豚鱼吉，利涉大川","binary":"110011"},
    {"num":62,"name":"雷山小过","symbol":"䷽","upper":"震","lower":"艮","palace":"兑宫","gua_ci":"亨，利贞，可小事","binary":"001100"},
    {"num":63,"name":"水火既济","symbol":"䷾","upper":"坎","lower":"离","palace":"坎宫","gua_ci":"亨小，利贞，初吉终乱","binary":"010101"},
    {"num":64,"name":"火水未济","symbol":"䷿","upper":"离","lower":"坎","palace":"离宫","gua_ci":"亨，小狐汔济，濡其尾","binary":"101010"},
]

# 详细策略（从天机爻Wiki详细解读提取，8卦完整）
detailed = {
    1: {
        "xiang_zhuan": "天行健，君子以自强不息",
        "tuan_zhuan": "大哉乾元，万物资始，乃统天",
        "key_yao": {"初九": "潜龙勿用——龙潜藏水中，暂不宜施展才能", "九二": "见龙在田——龙出现在田野，利于见到大人物", "九五": "飞龙在天——龙飞腾在天，达到鼎盛时期", "上九": "亢龙有悔——龙飞得过高，必将后悔"},
        "modern_application": "事业开创期宜积蓄力量等待时机；领导力发展展现才能但避免过度张扬；把握时机知进知退",
        "overall_judgment": "大吉之卦，但需注意物极必反",
        "source": "天机爻Wiki"
    },
    2: {
        "xiang_zhuan": "地势坤，君子以厚德载物",
        "tuan_zhuan": "至哉坤元，万物资生，乃顺承天",
        "key_yao": {"初六": "履霜，坚冰至——踩到薄霜，坚冰即将到来", "六二": "直方大，不习无不利——正直端方宏大，不学习也没有什么不利", "六五": "黄裳元吉——穿着黄色的下衣，大吉大利"},
        "modern_application": "团队合作以柔顺包容的态度配合领导；家庭关系体现母性的包容与滋养；投资理财稳健保守的策略更为适宜",
        "overall_judgment": "吉卦，强调柔顺之道，宜以静制动以柔克刚",
        "source": "天机爻Wiki"
    },
    3: {
        "xiang_zhuan": "云雷屯，君子以经纶",
        "tuan_zhuan": "",
        "key_yao": {"初九": "磐桓，利居贞——徘徊不前，利于安居守正", "六二": "屯如邅如，乘马班如——初创时期艰难徘徊", "上六": "乘马班如，泣血涟如——乘马的人犹豫不决，血泪涟涟"},
        "modern_application": "创业初期面临各种困难需要坚忍不拔；项目启动万事开头难需要周密规划；个人发展积累阶段不宜贸然行动",
        "overall_judgment": "初创艰难之象，虽有发展前景但阻力重重，宜守不宜攻",
        "source": "天机爻Wiki"
    },
    4: {
        "xiang_zhuan": "山下出泉，蒙。君子以果行育德",
        "tuan_zhuan": "",
        "key_yao": {"初六": "发蒙，利用刑人——启发蒙昧，利于树立规范", "九二": "包蒙吉，纳妇吉——包容蒙昧，吉祥", "上九": "击蒙，不利为寇，利御寇——打击蒙昧，不宜采取过激手段"},
        "modern_application": "教育培训启发引导而非强制灌输；个人学习保持谦虚好学的态度；管理指导耐心教导下属",
        "overall_judgment": "启蒙之象，需要虚心学习，应当寻求明师指导",
        "source": "天机爻Wiki"
    },
    5: {
        "xiang_zhuan": "云上于天，需。君子以饮食宴乐",
        "tuan_zhuan": "",
        "key_yao": {"初九": "需于郊，利用恒——在郊外等待，利于保持恒心", "九二": "需于沙，小有言，终吉——在沙滩上等待，稍有口舌，最终吉祥", "上六": "入于穴，有不速之客三人来——进入洞穴，有不请自来的三位客人"},
        "modern_application": "投资时机等待最佳入场时机；职业发展积累实力等待晋升机会；人际关系以诚信待人终获认可",
        "overall_judgment": "等待之象，需要耐心和诚信，时机未到不宜妄动",
        "source": "天机爻Wiki"
    },
    6: {
        "xiang_zhuan": "天与水违行，讼。君子以作事谋始",
        "tuan_zhuan": "",
        "key_yao": {"初六": "不永所事，小有言，终吉——不长久纠缠于争讼之事", "九二": "不克讼，归而逋——争讼不能获胜，回来逃避", "上九": "或锡之鞶带，终朝三褫之——或许被赐予官服大带，但一天之内被多次剥夺"},
        "modern_application": "法律纠纷宜和解不宜诉讼；商业竞争避免恶性竞争寻求合作；人际矛盾退一步海阔天空",
        "overall_judgment": "争讼之象，凶多吉少，应当避免争端以和为贵",
        "source": "天机爻Wiki"
    },
    11: {
        "xiang_zhuan": "天地交，泰。后以财成天地之道，辅相天地之宜",
        "tuan_zhuan": "",
        "key_yao": {"初九": "拔茅茹，以其汇——拔茅草时根系相连，象征同类相从", "九三": "无平不陂，无往不复——没有只平不坡的，没有只往不返的", "上六": "城复于隍——城墙倒塌在护城壕里"},
        "modern_application": "事业发展处于顺境但仍需居安思危；人际关系上下沟通顺畅合作无间；投资决策市场繁荣但需注意物极必反",
        "overall_judgment": "通泰之象，大吉大利，但需知泰极否来",
        "source": "天机爻Wiki"
    },
    12: {
        "xiang_zhuan": "天地不交，否。君子以俭德辟难，不可荣以禄",
        "tuan_zhuan": "",
        "key_yao": {"初六": "拔茅茹，以其汇——拔茅草时根系相连，坚守正道则吉祥", "六三": "包羞——包容羞辱", "上九": "倾否，先否后喜——倾覆闭塞，先闭塞后喜悦"},
        "modern_application": "事业困境时运不济宜保守忍耐；人际关系沟通不畅需要主动破冰；个人心态接受现实等待时机",
        "overall_judgment": "闭塞之象，诸事不顺，但否极泰来坚守正道终会好转",
        "source": "天机爻Wiki"
    }
}

# 合并基础数据+详细策略
hexagram_strategies = []
for h in hexagrams_base:
    entry = {
        "num": h["num"],
        "name": h["name"],
        "symbol": h["symbol"],
        "upper_trigram": h["upper"],
        "lower_trigram": h["lower"],
        "palace": h["palace"],
        "gua_ci": h["gua_ci"],
        "binary": h["binary"],
        "xiang_zhuan": "",
        "tuan_zhuan": "",
        "key_yao": {},
        "modern_application": "",
        "overall_judgment": "",
        "source": "天机爻Wiki"
    }
    if h["num"] in detailed:
        d = detailed[h["num"]]
        entry["xiang_zhuan"] = d["xiang_zhuan"]
        entry["tuan_zhuan"] = d["tuan_zhuan"]
        entry["key_yao"] = d["key_yao"]
        entry["modern_application"] = d["modern_application"]
        entry["overall_judgment"] = d["overall_judgment"]
        entry["source"] = d["source"]
    else:
        entry["xiang_zhuan"] = "待补充"
        entry["modern_application"] = "待补充"
        entry["overall_judgment"] = "待补充"
        entry["source"] = "天机爻Wiki（基础数据）"
    hexagram_strategies.append(entry)

base_data = {
    "meta": {
        "version": "1.0",
        "layer": "base",
        "description": "64卦策略基础层 — 权威底座，不可变",
        "source": "天机爻Wiki 64卦速查表 + 详细解读（8卦完整，56卦基础数据）",
        "source_url": "https://wiki.tianjiyao.com/yijing/hexagrams.html",
        "created": "2026-08-03",
        "completeness": "64/64卦辞完整，8/64详细策略完整，56/64象传爻辞待补充",
        "notes": "详细策略（象传/爻辞/现代应用）目前完整覆盖8卦（乾坤屯蒙需讼泰否），其余56卦有卦辞和基础信息，象传待从周易原文补充"
    },
    "hexagrams": hexagram_strategies
}

# ============================================================
# 3. hexagram_strategies_custom.json — 个人定制层
#    来源：乐安生个人64卦策略笔记
# ============================================================

custom_notes = {
    1: {"strategy": "前期苟着发育，中后期进攻信号，不停开拓进攻", "key_phrase": "你好刚"},
    2: {"strategy": "以静制动，防守反击，稳住别犯病，对面自己会犯病", "key_phrase": "哇，好多"},
    3: {"strategy": "四大凶卦之一，开头难，必须行动才有生机，过程出差错就炸", "key_phrase": "君子报仇十年不晚"},
    4: {"strategy": "懵懂无知，需要启蒙，易犯小人被蒙蔽", "key_phrase": "我不知道啊"},
    5: {"strategy": "万事俱备只欠东风，缺时机，需外力点燃，只能等。该吃吃该喝喝", "key_phrase": "云上于天，需君子以饮食宴乐"},
    6: {"strategy": "事与愿违诸事不顺，与队友意见不一致，宜防陷阱小人", "key_phrase": "你居然和我哔哔"},
    7: {"strategy": "", "key_phrase": ""},
    8: {"strategy": "平顺吉利，贵人相助，速战速决，不当独行侠，成双成对，人到齐则吉", "key_phrase": "兄弟们一起干他"},
    9: {"strategy": "时机不成熟，短时间难解决，能力不足。自己有能力创造时机", "key_phrase": "就知道画大饼"},
    10: {"strategy": "如沼泽中行走，乱挣扎就寄，要提前预想，有心理准备遇事不慌。可有惊无险", "key_phrase": "虚惊一场"},
    11: {"strategy": "三阳开泰，运势转昌盛，诸事顺利", "key_phrase": ""},
    12: {"strategy": "阴阳不交闭塞不通，百事不顺倒霉开始。凡事宜忍，不忍容易寄掉", "key_phrase": "你要倒霉了"},
    13: {"strategy": "（低分局）志同道合目标一致则吉", "key_phrase": "这里都是我的人。天与火同人君子以类族辨物"},
    14: {"strategy": "大吉，天时地利人和，好机遇自己来就看接不接得住，有保底", "key_phrase": "要啥有啥"},
    15: {"strategy": "", "key_phrase": ""},
    16: {"strategy": "", "key_phrase": ""},
    17: {"strategy": "", "key_phrase": ""},
    18: {"strategy": "", "key_phrase": ""},
    19: {"strategy": "临利主导，当主角站出来主导，就有贵人或好运相助兜底", "key_phrase": "让我亲自试试"},
    20: {"strategy": "风口浪尖暂不明朗，驻足观察先", "key_phrase": "我看见了"},
    21: {"strategy": "诸事阻隔纷争难免，如鲠在喉，需找人帮忙疏通", "key_phrase": "咬牙切齿"},
    22: {"strategy": "", "key_phrase": ""},
    23: {"strategy": "大凶，厄运缠身不宜自作聪明，防被女子小人针对。从外到内一层层崩溃，能保住不死就不错。队友发病或情况不对直接卖，只能保有生力量", "key_phrase": "你在剥削我"},
    24: {"strategy": "", "key_phrase": ""},
    25: {"strategy": "墨守成规按规矩做事则吉，不按规矩必无妄之灾，不要以身犯险，遇事拿最稳妥做法", "key_phrase": "小心被雷劈"},
    26: {"strategy": "对手暂时无法战胜给阻碍但阻止不了我们，先忍着忍耐就是吉利", "key_phrase": "有钱人"},
    27: {"strategy": "闷声做事当老六", "key_phrase": ""},
    28: {"strategy": "", "key_phrase": ""},
    29: {"strategy": "危机四伏。前面有坑。四大凶卦，坎坷重重无立足之地", "key_phrase": ""},
    30: {"strategy": "开始很烫不要靠近会被烫伤，等凉了再进场收割。局势明朗偏吉，但容易意气用事冲动上头", "key_phrase": "好漂亮"},
    31: {"strategy": "君子以虚受人。无心之感吉祥如意，按第一感觉自然而成。配合得当重在配合", "key_phrase": "处个对象呗"},
    32: {"strategy": "", "key_phrase": ""},
    33: {"strategy": "以退为进，后退为推进，不露面拿队友钓鱼", "key_phrase": "兄弟我先走了"},
    34: {"strategy": "", "key_phrase": ""},
    35: {"strategy": "环境有利于操作上进，需要一定能力", "key_phrase": "上进点"},
    36: {"strategy": "天黑了看不清，静待时机切勿盲目行动。小人加害困难重重，忍耐待机", "key_phrase": "遇事不要迷。都在潜水"},
    37: {"strategy": "", "key_phrase": ""},
    38: {"strategy": "", "key_phrase": ""},
    39: {"strategy": "四大凶之一，进退两难多灾多难", "key_phrase": "行动不便"},
    40: {"strategy": "", "key_phrase": ""},
    41: {"strategy": "为向上或胜利要舍得损失，卖自己或拿资源跟对面换", "key_phrase": ""},
    42: {"strategy": "气势强风快雷，自信不懦已赢一半。赚得盆满钵满", "key_phrase": ""},
    43: {"strategy": "讲究决策效率，打不打要快，决定了贯彻到底越犹豫越凶", "key_phrase": "快点决定走不走"},
    44: {"strategy": "相遇邂逅不期而遇，多走出去碰运气，有意外之喜也有意外之灾", "key_phrase": "好强大的女人"},
    45: {"strategy": "得贵人帮助，出现有利环境滋养你", "key_phrase": "不是一家人不进一家门"},
    46: {"strategy": "步步高升晋升之相，主指自己提升优先考虑自己", "key_phrase": "6的飞起"},
    47: {"strategy": "", "key_phrase": ""},
    48: {"strategy": "萧规曹随，以不变应万变", "key_phrase": "跑得了和尚跑不了庙"},
    49: {"strategy": "", "key_phrase": ""},
    50: {"strategy": "三人成行鼎足而立，配方正确慢慢做熟，时运是对的只要好好干就向好。革故鼎新", "key_phrase": "生米煮成熟饭"},
    51: {"strategy": "", "key_phrase": ""},
    52: {"strategy": "两山重叠障碍重重，过了一关还有一关。不要轻易尝试，越往前路越窄想回头来时路没了。推进阻碍多宜量力而行", "key_phrase": "行了行了就这样"},
    53: {"strategy": "", "key_phrase": ""},
    54: {"strategy": "处事走违常理，先得其益后祸害百出", "key_phrase": "快跑，你老婆来了"},
    55: {"strategy": "短时间时机很好，顺时而动收获不小。看情况别贪", "key_phrase": "无所畏惧"},
    56: {"strategy": "带来烦躁，诸事变动不定，不可预测的变动令人烦躁不安", "key_phrase": "开场说走就走的旅行"},
    57: {"strategy": "顺风可跟进得益，逆风可轻松退出，进退自如来去如风", "key_phrase": "你说得对"},
    58: {"strategy": "", "key_phrase": ""},
    59: {"strategy": "", "key_phrase": ""},
    60: {"strategy": "会有一定收获但之后要保持节制别贪。水满了再加就溢出", "key_phrase": "克制一点"},
    61: {"strategy": "", "key_phrase": ""},
    62: {"strategy": "多劳少得", "key_phrase": ""},
    63: {"strategy": "事情已成，正常打慢慢来功到自然成，主要思考成了之后的事", "key_phrase": "大功告成"},
    64: {"strategy": "", "key_phrase": ""},
}

custom_data = {
    "meta": {
        "version": "1.0",
        "layer": "custom",
        "description": "个人定制层 — 乐安生个人64卦策略笔记，可随时替换",
        "source": "乐安生个人积累",
        "created": "2026-08-03",
        "completeness": f"{sum(1 for v in custom_notes.values() if v['strategy'])}/64卦有个人策略",
        "notes": "空白卦位运行时自动用base层兜底。可热插拔：替换此文件即生效，不影响base层",
        "hot_swappable": True
    },
    "hexagrams": [
        {
            "num": num,
            "name": next(h["name"] for h in hexagrams_base if h["num"] == num),
            "personal_strategy": custom_notes[num]["strategy"],
            "key_phrase": custom_notes[num]["key_phrase"],
            "source": "乐安生个人笔记"
        }
        for num in range(1, 65)
    ]
}

# ============================================================
# 写入文件
# ============================================================

files = {
    "trigram_table.json": trigram_data,
    "hexagram_strategies_base.json": base_data,
    "hexagram_strategies_custom.json": custom_data,
}

for filename, data in files.items():
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    size = os.path.getsize(filepath)
    print(f"✅ {filename} — {size:,} bytes")

# 验证
print("\n--- 验证 ---")
for filename in files:
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "trigrams" in data:
        print(f"trigram_table: {len(data['trigrams'])} trigrams, {len(data['twelve_message_hexagrams'])} message hexagrams")
    elif data["meta"]["layer"] == "base":
        print(f"base layer: {len(data['hexagrams'])} hexagrams, {sum(1 for h in data['hexagrams'] if h['xiang_zhuan'] != '待补充')} detailed")
    elif data["meta"]["layer"] == "custom":
        filled = sum(1 for h in data['hexagrams'] if h['personal_strategy'])
        print(f"custom layer: {len(data['hexagrams'])} hexagrams, {filled} with personal strategy")
