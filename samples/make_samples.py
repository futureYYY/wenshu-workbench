"""生成示例文件（只用标准库，任何 Python 3.10+ 都能运行）。

    python samples/make_samples.py

输出：
- samples/客服对话-意图识别.xlsx   工作表“对话”约 120 行（会话ID、用户问题、时间、渠道）+ 工作表“说明”
- samples/客服对话-意图识别.csv    UTF-8 带 BOM、逗号分隔，约 100 行，含一个引号内带换行的字段
- samples/客服长文本-文本摘要.txt  每行一篇较长的客服记录，用于文本摘要（含两篇超过 3,000 字的长文）
- frontend/e2e/fixtures/intent_200.xlsx  端到端测试用（结构见 docs/08 第 10.2 节）

xlsx 用 zipfile 手写 SpreadsheetML（共享字符串、样式、冻结首行），Excel、openpyxl、python-calamine 都能打开。
全部内容是虚构的客服场景，不含真实个人信息。随机数固定种子，每次生成的内容相同。
"""

from __future__ import annotations

import csv
import io
import random
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
XLSX_SAMPLE = HERE / "客服对话-意图识别.xlsx"
CSV_SAMPLE = HERE / "客服对话-意图识别.csv"
TXT_SAMPLE = HERE / "客服长文本-文本摘要.txt"
E2E_FIXTURE = ROOT / "frontend" / "e2e" / "fixtures" / "intent_200.xlsx"

CHANNELS = ["App", "电话", "微信", "网页", "小程序"]
LEVELS = ["普通", "普通", "银卡", "金卡", "黑金"]

# ---------------------------------------------------------------- 意图识别：用户问题

QUESTIONS: dict[str, list[str]] = {
    "咨询": [
        "我的快递三天没动了，能帮我查一下吗",
        "退款一般多久能到账",
        "会员每个月多少钱，可以按年买吗",
        "你们开的发票是电子的还是纸质的",
        "积分什么时候过期",
        "下单以后还能修改收货地址吗",
        "七天无理由退货的运费谁出",
        "保修期是从签收那天开始算吗",
        "晚上几点之前下单可以当天发货",
        "你们支持货到付款吗",
        "优惠券和满减可以一起用吗",
        "商品显示预售是什么意思，大概什么时候发货",
        "换货需要寄回原包装吗",
        "订单为什么一直显示待审核",
        "附近有没有可以自提的门店",
        "海外地址能不能寄",
        "积分可以抵扣运费吗",
        "退货地址是哪里，需要写什么备注",
        "会员的免邮次数每个月有几次",
        "空调安装要另外收费吗",
        "以旧换新的旧机怎么估价",
        "价保是怎么算的，降价了能退差价吗",
        "发票能开到个人名下吗",
        "快递显示已签收但我没收到，怎么回事",
        "学生认证以后有什么优惠",
    ],
    "办理": [
        "帮我把会员自动续费取消掉",
        "我要退订营销短信",
        "请帮我开一张公司抬头的增值税专用发票",
        "我想把收货人电话改成新的号码",
        "麻烦帮我申请退款，订单号在上面",
        "帮我把这单改成到店自提",
        "我要注销账号",
        "请帮我开通企业采购权限",
        "帮我把订单拆成两次发货",
        "申请换货，鞋子尺码大了一号",
        "我要升级成年度会员",
        "请帮我预约上门维修，空调不制冷",
        "帮我取消还没发货的那个订单",
        "我想把绑定的手机号换掉",
        "帮我补开一下上个月的发票",
        "请帮我把积分转到家人的账户",
        "帮我预约明天上午安装热水器",
        "我要修改实名认证的信息",
    ],
    "投诉": [
        "我要投诉你们的快递员，东西直接扔在门口",
        "买了不到一周就坏了，你们必须给个说法",
        "客服电话打了五次都没人接，太差劲了",
        "说好的二十四小时退款，现在一周了还没到",
        "收到的商品和图片完全不一样，我要求赔偿",
        "外卖送错了还态度很差，我要投诉",
        "维修师傅上门迟到两个小时还多收费",
        "自动续费没有任何提醒就扣了我的钱",
        "积分莫名其妙被清零了，你们怎么解释",
        "发票拖了半个月还没开出来",
        "买到的鸡蛋碎了一半，客服还让我自己承担",
        "安装师傅把墙打坏了不管，我要投诉",
        "同一个问题反映三次了，每次都说会处理",
    ],
    "建议": [
        "建议你们App增加夜间模式",
        "希望退款进度能在订单页面直接看到",
        "建议会员到期前多提醒几次",
        "能不能在下单页面就显示预计送达时间",
        "希望客服机器人能更快转人工",
        "建议发票可以批量下载",
        "包装可以少用点塑料，太浪费了",
        "希望增加按发票号查询订单的功能",
        "建议售后上门前半小时打个电话",
        "希望能按收货地址合并发货，省得收好几个包裹",
    ],
    "其他": [
        "你好",
        "在吗",
        "谢谢，没事了",
        "哈哈",
        "测试一下",
        "嗯",
        "我先看看",
        "好的知道了",
        "刚才点错了",
    ],
}

PREFIXES = ["", "", "", "你好，", "您好，", "麻烦问一下，", "客服你好，", "请问"]
SUFFIXES = ["", "", "", "，谢谢", "，急", "？", "，在线等", "，麻烦尽快"]


def question_pool() -> list[str]:
    pool: list[str] = []
    for items in QUESTIONS.values():
        pool.extend(items)
    return pool


def varied_questions(rng: random.Random, count: int) -> list[str]:
    """从基础问题出发，加上常见的开头和结尾，生成 count 条互不相同的问题。"""
    base = question_pool()
    seen: set[str] = set()
    result: list[str] = []
    order = base[:]
    rng.shuffle(order)
    # 先放每条基础问题本身，再放加了开头、结尾的变体
    for text in order:
        if len(result) >= count:
            break
        if text not in seen:
            seen.add(text)
            result.append(text)
    guard = 0
    while len(result) < count and guard < 100_000:
        guard += 1
        text = rng.choice(base)
        prefix = rng.choice(PREFIXES)
        suffix = rng.choice(SUFFIXES)
        if text in QUESTIONS["其他"] and (prefix or suffix):
            continue  # 寒暄类保持原样
        if prefix == "请问" and not text.endswith(("吗", "么", "呢", "没")):
            prefix = "请问一下，"
        candidate = f"{prefix}{text}{suffix}"
        if candidate.endswith("？？"):
            candidate = candidate[:-1]
        if candidate not in seen:
            seen.add(candidate)
            result.append(candidate)
    return result


def dialogue_rows(rng: random.Random, *, unique: int, duplicates: int, blanks: int, start: datetime) -> list[list[object]]:
    """表头 + 数据行：会话ID、用户问题、时间、渠道。duplicates 行重复前面的问题，blanks 行问题为空。"""
    questions: list[str] = varied_questions(rng, unique)
    texts: list[str] = questions[:]
    for _ in range(duplicates):
        position = rng.randint(len(texts) // 3, len(texts))
        texts.insert(position, rng.choice(questions[: max(1, position - 1)]))
    for _ in range(blanks):
        texts.insert(rng.randint(5, len(texts) - 1), "")
    rows: list[list[object]] = [["会话ID", "用户问题", "时间", "渠道"]]
    moment = start
    # 第一条固定用文档里的例子，便于对照
    if "我的快递三天没动了，能帮我查一下吗" in texts:
        texts.remove("我的快递三天没动了，能帮我查一下吗")
    texts.insert(0, "我的快递三天没动了，能帮我查一下吗")
    for index, text in enumerate(texts):
        moment += timedelta(minutes=rng.randint(1, 37), seconds=rng.randint(0, 59))
        rows.append([10023 + index, text, moment, rng.choice(CHANNELS)])
    return rows


# ---------------------------------------------------------------- 文本摘要：长文本

LETTER_DELIVERY = (
    "您好，我是在贵平台购物多年的老用户，今天写这封信是想投诉一笔订单的物流问题。"
    "我在九月二十八日下单购买了一台空气净化器，订单页面承诺四十八小时内发货、五天内送达。"
    "结果商品在九月三十日才发出，此后物流信息在中转站停留了整整六天，没有任何更新。"
    "期间我先后三次联系在线客服，每次得到的答复都是已经催促快递公司，请耐心等待，但没有任何人告诉我包裹到底在哪里、什么时候能到。"
    "十月七日我再次拨打客服热线，排队四十分钟才接通，客服人员表示包裹可能已经丢失，需要再等三个工作日核实。"
    "我购买净化器是因为家里刚装修完，老人和孩子都在等着用，这样的拖延让我非常失望。"
    "更让我不能接受的是，在这十天里，平台没有主动给我发过一条通知，所有的信息都是我自己一次次去问出来的。"
    "我希望贵平台尽快查明包裹的下落，如果确认丢失，请直接为我补发一台或者全额退款，并补偿相应的时间成本。"
    "另外我也建议贵平台加强对合作快递公司的考核，在物流长时间停滞时主动通知用户，而不是让用户自己去催。"
    "如果三个工作日内仍然没有结果，我会考虑向消费者协会反映。期待尽快收到答复，谢谢。"
)

REFUND_DISPUTE = (
    "【通话纪要】工单号 RF20261003-0417。客户反映在平台购买的一套羽绒被申请退货后迟迟没有收到退款，以下为本工单的全部沟通记录，按时间顺序整理。"
    "背景：客户于九月二十二日下单购买双人羽绒被一套，实付八百九十九元，九月二十五日签收后发现被芯有明显异味，且充绒量与详情页描述不符，当天在订单页面申请七天无理由退货并选择上门取件。"
    "九月二十六日快递员上门取走商品，物流显示九月二十八日商家已签收退货。"
    "十月三日第一次来电：客户表示退货已被商家签收五天，但退款仍显示商家处理中，询问退款什么时候能到账。"
    "客服查询后告知，商家需要在签收后四十八小时内完成验货，目前已经超时，平台将发起催办，并承诺二十四小时内给出处理结果。"
    "客户表示理解，但希望尽快处理，因为这笔钱是用信用卡支付的，账单日快到了。"
    "十月四日系统记录：平台向商家发起催办，商家回复称退回的商品有使用痕迹，被套上有污渍，申请拒绝退款，并上传了三张照片。"
    "十月五日第二次来电：客户收到拒绝退款的通知后情绪激动，表示收到商品当天就发现了异味，根本没有使用过，所谓的污渍是商品本身就有的，自己签收时还拍了开箱视频。"
    "客服请客户通过订单页面的上传凭证入口提交开箱视频和签收当天的照片，并说明平台会介入判定，判定周期为三到五个工作日。"
    "客户追问能否先行退款，客服解释先行退款需要满足信用评级等条件，客户的账户符合条件，但该订单已经进入纠纷流程，需要等待判定结果。"
    "客户表示不满，认为平台偏袒商家，要求升级处理，客服记录了客户诉求并提交给纠纷处理组。"
    "十月六日系统记录：客户上传开箱视频一段、照片五张，纠纷处理组受理，要求商家在四十八小时内补充举证。"
    "十月八日第三次来电：客户询问进度，并表示信用卡账单已经出来，八百九十九元已经计入当期账单，如果再不退款就要先自己垫付。"
    "客服查询到商家已经补充举证，但举证照片的拍摄时间晚于商家签收时间两天，且无法证明污渍来自客户使用，纠纷处理组初步倾向支持客户。"
    "客服向客户说明了进展，并承诺判定结果出来后第一时间电话告知。"
    "客户提出能否补偿因延误带来的不便，客服表示可以在判定结束后为客户申请一张五十元无门槛优惠券，客户表示可以接受，但强调最重要的是尽快退款。"
    "十月九日系统记录：纠纷判定结果为支持买家，平台判定商家全额退款，并对商家虚假举证记录违规一次；八百九十九元已原路退回客户信用卡，预计一到三个工作日到账。"
    "十月九日第四次通话（客服回访）：客服致电客户告知判定结果和到账时间，客户表示感谢，同时反映整个过程耗时太长，从退货签收到收到退款将近两周，期间自己打了四次电话。"
    "客户希望平台缩短商家验货的时限，超时后自动退款，而不是由用户反复催促，客服记录了这条建议，并说明会转交给产品团队。"
    "客户另外询问五十元优惠券何时发放，客服确认已经提交申请，二十四小时内到账，有效期三十天。"
    "十月十一日系统记录：优惠券已发放至客户账户，客户的信用卡退款已到账，客户在服务评价中打了三星，留言结果满意、过程太慢。"
    "处理总结：本工单的核心问题是商家超时验货，并以证据不足的理由拒绝退款，导致退款周期被拉长；平台介入后，依据客户提供的开箱视频作出了支持买家的判定。"
    "后续改进建议有三点：一是对超过验货时限的退货订单自动触发退款；二是要求拒绝退款的商家同步上传带时间戳的验货视频；三是纠纷处理期间主动向客户推送进度，减少客户来电次数。"
)

MEMBERSHIP_RENEWAL = (
    "客服中心：你们好。我在十月一日收到银行短信，提示我的账户被扣了二百四十八元，备注是年度会员自动续费。"
    "我记得去年开通会员时选的是首月体验，当时页面上写的是到期自动结束，并没有看到会自动按年续费的提示。"
    "我翻了一下订单记录，发现开通页面最下面有一行很小的灰色文字，写着默认开启自动续费，可以随时在设置里关闭。"
    "说实话，这样的设计很难让人注意到，我相信很多用户和我一样是被动续费的。"
    "更重要的是，扣费之前我没有收到任何提醒，既没有短信，也没有 App 推送，邮箱里也没有。"
    "按照我了解到的规定，自动续费前应当以显著方式提前告知用户，你们的做法显然不符合要求。"
    "过去一年里我只用了两次会员的免邮权益，续费一年对我来说完全没有必要。"
    "我已经在 App 里关闭了自动续费，但这次扣掉的二百四十八元还没有退回。"
    "我联系过在线客服，对方说会员已经生效，只能按剩余天数折算退款，而且要扣除已经享受的权益价值，算下来只能退一百多元。"
    "我认为这个处理不合理，扣费是在我不知情的情况下发生的，续费之后我也没有使用过任何会员权益，应该全额退款。"
    "希望你们能尽快核实，全额退还这笔费用，并在以后的续费前用短信和推送提前三天提醒用户。"
    "如果需要我提供银行扣款记录的截图，我可以随时补充。"
)

INVOICE_ISSUE = (
    "您好，我们公司在九月份通过贵平台采购了一批办公用品，共三个订单，合计一万二千六百元。"
    "下单时已经在发票信息里填写了公司抬头和税号，并选择了增值税专用发票。"
    "但是到现在过去了二十多天，只有一个订单开出了发票，另外两个订单的发票状态一直显示开票中。"
    "这两个订单分别是九月九日的打印纸和硒鼓，金额四千三百元，以及九月十八日的办公椅，金额五千一百元。"
    "我们财务月底要做报销和进项抵扣，如果本月拿不到发票，这部分税额就只能顺延到下个月处理，会影响我们的报税安排。"
    "我联系过两次在线客服，第一次说三个工作日内开出，第二次说商家那边在核对开票信息，但都没有下文。"
    "我们核对过订单里填写的抬头、税号、开户行和账号，和营业执照完全一致，同一套信息开出的第一张发票也没有问题。"
    "请帮忙查一下具体卡在哪个环节，如果是信息有误，请告诉我们需要补充什么材料；如果是商家的问题，请平台帮忙督促。"
    "另外，希望以后发票开具超过七天时，系统能主动通知申请人，并显示当前进度，方便我们及时跟进。"
)

ACCOUNT_APPEAL = (
    "账号申诉说明：本人是该账号的注册使用者，账号注册已有五年，一直绑定本人的手机号和银行卡。"
    "十月十二日晚上十点左右，我收到一条短信验证码，提示有人在异地登录我的账号，我当时没有在意，以为是骚扰短信。"
    "第二天早上我打开 App，发现登录密码已经被修改，绑定的手机号也被换成了一个陌生号码，我已经无法登录。"
    "我立即通过找回密码功能尝试找回，但系统提示验证码会发送到新绑定的手机号，我没有办法收到。"
    "随后我拨打了客服电话，客服帮我临时冻结了账号，并告诉我需要通过人工申诉找回。"
    "根据冻结前看到的信息，对方在我的账号里下了两笔订单，分别是一部手机和两张购物卡，合计约五千三百元，使用的是账户里绑定的银行卡快捷支付。"
    "其中购物卡订单已经显示完成，卡密已被提取；手机订单显示待发货。"
    "我已经联系银行冻结了这张银行卡，并在当地派出所报案，取得了报案回执。"
    "现在提交申诉材料，包括身份证正反面照片、手持身份证照片、银行卡流水截图、报案回执，以及过去一年的几笔常用收货地址和订单号，用于证明账号归属。"
    "我的诉求有三点：第一，尽快把账号恢复到我本人名下，重新绑定我的手机号；第二，拦截还没有发货的手机订单，并协助追回已经被提取的购物卡金额；第三，查明账号被盗的原因。"
    "我平时使用的密码比较复杂，也没有在其他网站使用相同密码，不清楚对方是如何拿到验证码的。"
    "我注意到对方修改手机号时只需要短信验证码，没有任何二次确认，这一点希望平台能加强，例如在更换绑定手机号时要求人脸识别，或者给原手机号发送提醒并设置二十四小时的冷静期。"
    "我理解申诉审核需要时间，但涉及的金额较大，恳请加快处理。"
    "我的联系方式已经填写在申诉表里，工作日白天都可以接听电话，如需补充材料请随时通知。"
)

POINTS_CLEARED = (
    "我要投诉积分被清零的问题。我从二〇二二年开始在你们这里购物，一直攒积分，到上个月为止账户里有一万八千多积分，本来打算双十一的时候抵扣使用。"
    "十月十五日我登录 App，发现积分只剩下三百多，积分明细里显示十月一日有一条积分过期扣除的记录，扣掉了一万七千多。"
    "我完全不知道积分会过期，开户时没有人告诉我，平时也从来没有收到过任何过期提醒。"
    "我查了一下积分规则，现在的规则说积分有效期为两年，但我记得以前的规则是长期有效，规则是什么时候改的，有没有通知过用户，我都不清楚。"
    "就算规则改了，你们也应该在积分过期前提醒用户，至少应该提前一个月发短信或者推送，而不是一声不响地清零。"
    "一万七千积分按照抵扣比例大概相当于一百七十元，金额不算特别大，但这是我几年来一点点攒下的，这种做法让我觉得很不被尊重。"
    "我也问过在线客服，客服只是复制了一遍积分规则给我，说过期积分无法恢复，对于为什么没有提醒一句都没有解释。"
    "我要求恢复被清零的积分，或者给出合理的补偿；同时希望你们修改积分过期的提醒机制，避免其他用户遇到同样的问题。"
    "如果这件事得不到合理处理，我会考虑不再使用你们的平台。"
)

SUGGESTIONS = (
    "十月用户建议汇总（来源：App 意见反馈、客服工单、用户访谈）。"
    "本月共收到有效建议三百一十二条，按主题归类后，排在前面的几类如下。"
    "第一类是物流与配送，共九十六条。用户最希望在下单页面直接看到预计送达时间，而不是付款之后才知道；其次是希望同一地址的多个订单能够合并发货，减少收快递的次数；还有用户提出夜间配送时不要打电话，改为短信通知。"
    "第二类是售后与退款，共七十四条。用户普遍希望退款进度能在订单页面实时显示，包括商家是否已签收退货、是否已验货、预计到账时间；也有用户建议超过验货时限后自动退款。"
    "第三类是客服体验，共五十八条。主要集中在智能客服转人工太慢、排队时间不透明、同一问题需要反复描述。有用户建议在转人工时把之前的对话自动带给人工客服。"
    "第四类是会员与积分，共四十一条。用户希望会员到期和自动续费前多提醒几次，积分过期前至少提前一个月通知，并且在积分明细里显示每一笔积分的到期日期。"
    "第五类是 App 功能，共四十三条。呼声最高的是增加夜间模式，其次是发票批量下载、按发票号查询订单、订单列表支持按商品名搜索。"
    "此外还有一些零散建议，例如减少包装里的塑料填充物、为老年用户提供大字模式、在维修上门前半小时电话通知。"
    "产品团队已经把物流时效展示、退款进度展示和积分到期提醒列入下季度的优先事项，其余建议会在评审后陆续答复。"
    "建议汇总会继续每月更新，欢迎各业务线补充来自一线的反馈。"
)

BROADBAND = (
    "工单备注：客户九月二十日办理了千兆宽带，约定九月二十四日上门安装。"
    "二十四日安装师傅临时通知改到二十六日，客户请了半天假在家等候，二十六日下午又被告知设备没有到货，安装再次推迟。"
    "十月三日客户第三次来电，表示已经被改期两次，每次都是当天才通知，要求明确安装时间，并对已经扣除的首月月租提出异议。"
    "客服核实后确认是片区装维人员不足导致排期混乱，已经为客户锁定十月五日上午九点到十一点的时段，并承诺若再次延误将免除前三个月月租。"
    "首月月租从实际开通之日起计算，已扣费用将在下个账单周期退还。客户表示接受，要求安装前一天短信确认。"
    "客户还提到自己在家办公，每天上午有视频会议，这一周只能用手机热点，流量费用多出了六十多元，希望一并考虑。"
    "客服说明流量费用属于其他运营商的账单，无法直接报销，但可以为客户申请赠送三个月的网络提速包作为补偿，客户同意。"
    "十月五日上午装维人员按时上门，完成了光纤入户和光猫、路由器的安装，测速达到签约速率，客户在回访中表示满意。"
)


def repair_weekly() -> str:
    """售后维修周报：由十六条工单摘要组成的长文（超过 4,000 字）。"""
    orders = [
        "工单 WX1008-01：客户反映家里的滚筒洗衣机在脱水阶段撞击声很大，机身明显移位。工程师十月八日上午上门检查，发现运输固定螺栓没有拆除，属于安装时遗漏。工程师当场拆除了四颗固定螺栓并重新调平底脚，试运行一个完整的洗涤程序后噪音恢复正常。问题出在安装环节，本次上门不收费，安装网点被记录一次质量问题。客户对结果满意，但希望安装完成后能有人当面演示检查要点。",
        "工单 WX1008-02：客户反映空调制冷效果很差，室内温度一直降不下来。工程师检测发现系统压力偏低，存在缓慢泄漏，泄漏点位于室外机连接管的喇叭口。工程师重新制作喇叭口并补充冷媒，制冷恢复正常。由于机器已过三年保修期，按收费标准收取冷媒和人工费用共三百二十元。客户对收费有异议，认为空调才用了四年就漏氟，工程师现场出示了收费标准，客户最终同意支付，但要求在系统里备注，如果一年内再次泄漏要免费处理。",
        "工单 WX1009-03：客户的双开门冰箱冷藏室后壁结了厚厚一层冰，蔬菜被冻坏。工程师检查发现温度传感器阻值异常，导致压缩机持续运行。冰箱仍在保修期内，工程师更换了传感器并为冰箱化霜，叮嘱客户二十四小时后再放入食物。客户询问被冻坏的食物能否赔偿，工程师解释保修范围不包括食物损失，但可以帮客户申请一张一百元的延保优惠券，客户表示接受。",
        "工单 WX1009-04：客户反映电热水器底部漏水。工程师拆开外壳后发现内胆焊缝锈穿，需要整体更换内胆。热水器已使用九年，早已过保，更换内胆的报价接近新机价格的六成。工程师建议客户直接更换新机，并介绍了以旧换新补贴。客户表示需要和家人商量，工程师先关闭了进水阀并断电，确保安全，工单状态改为待客户确认。",
        "工单 WX1010-05：客户反映油烟机噪音越来越大，吸力明显下降。工程师检查发现风轮和油网积油严重，风轮已经轻微变形。工程师进行了深度清洗，并对风轮做了动平衡校正，噪音明显减小。按照清洗服务标准收取一百五十元。客户认为清洗价格偏高，工程师说明了深度清洗需要拆下电机，与普通清洗不同。客户接受了解释，并预约了半年后的再次清洗。",
        "工单 WX1010-06：客户反映电视开机有声音没有图像。工程师判断为背光灯条故障，电视在保修期内，可以免费更换，但同型号灯条需要从总仓调货，预计五个工作日到货。客户对等待时间不满，表示家里老人每天都要看电视。工程师为客户申请了临时借用一台小尺寸电视，第二天送到客户家中，客户对这一安排表示感谢。",
        "工单 WX1011-07：客户反映扫地机器人清扫结束后找不到充电座，经常停在客厅中间没电。工程师远程查看设备日志，发现是固件版本过旧导致回充定位异常。工程师指导客户在 App 中完成固件升级，并重新建图，测试三次回充均成功，本工单通过远程方式解决，无需上门。",
        "工单 WX1011-08：客户反映洗碗机洗完后底部积水，无法排干。工程师上门发现排水管在橱柜里被杂物挤压弯折，导致排水不畅。工程师重新整理了排水管走向并加装了固定卡扣，试机排水正常。问题与产品质量无关，但属于安装位置不合理，本次不收费，同时提醒客户橱柜里不要堆放过多物品。",
        "工单 WX1012-09：客户反映空调外机运行时有很大的振动声，楼下邻居已经来投诉。工程师上门发现外机支架有一颗膨胀螺栓松动，外机与墙面之间产生共振。工程师更换了膨胀螺栓并加装减震垫，振动声明显减小。外机位于六楼外墙，属于高空作业，按标准收取高空作业费一百元。客户对是否应该收费提出疑问，工程师解释支架属于客户自购配件，不在保修范围内。",
        "工单 WX1012-10：客户反映净水器出水越来越慢，水的味道也不好。工程师检查后确认前置滤芯和反渗透膜都已超过使用期限，为客户更换了全套滤芯，费用四百六十元。客户表示不知道滤芯需要定期更换，工程师帮客户在 App 里开通了滤芯到期提醒，并建议客户考虑滤芯订阅服务，客户表示会考虑。",
        "工单 WX1013-11：客户反映微波炉通电后转盘正常转动，但食物不加热。工程师检测确认磁控管损坏，微波炉已使用六年，维修费用约为新机价格的一半。客户决定放弃维修，工程师为客户登记了旧机回收，并发放了一张八十元的以旧换新券，客户对处理方式满意。",
        "工单 WX1013-12：客户来电反映燃气灶打不着火，担心燃气泄漏。客服先确认客户家中没有燃气异味，随后指导客户检查灶具底部的电池，发现电池电量耗尽。客户更换电池后灶具恢复正常，本工单电话解决，无需上门。客服同时提醒客户，如果闻到燃气味要先关闭总阀并开窗通风。",
        "工单 WX1014-13：客户反映冰箱门关不严，门封条有裂口。工程师为客户更换了冷藏室门封条，配件费一百二十元，人工费五十元。客户认为一条门封条一百二十元价格过高，在网上能买到便宜很多的同款。工程师解释原厂配件与网上通用件在尺寸和磁性上有差异，客户仍然不认可，表示要投诉配件价格，客服已记录客户意见并反馈给配件定价部门。",
        "工单 WX1014-14：客户投诉维修师傅迟到。客户预约的上门时间是上午九点到十一点，师傅实际在下午一点才到达，期间没有任何电话通知，客户为此请了一整天假。经核实，师傅当天上一单维修时间过长，没有及时调整后续安排，也没有提前联系客户。客服向客户致歉，免除了本次上门费，并补偿五十元话费，同时对该网点提出整改要求，要求师傅在可能迟到时提前半小时电话告知。",
        "工单 WX1015-15：客户反映空调遥控器失灵，更换电池后仍然没有反应。客服判断遥控器发射管损坏，遥控器属于随机配件，在保修期内，为客户免费寄送了一个新的遥控器，预计两天送达，并告知客户在收到之前可以通过空调 App 控制。",
        "工单 WX1015-16：客户反映家用投影仪画面偏色，整体发绿。工程师检查发现色轮电机故障，需要返厂维修，维修周期约十个工作日。投影仪在保修期内，返厂维修免费。客户担心周末家庭观影受影响，工程师为客户申请了一台备用机，与返厂取件同时送达，客户对此安排满意。",
        "工单 WX1016-17：客户来电称洗衣机洗完后门锁一直打不开，里面锁着第二天出差要穿的衣服，情绪比较着急。客服先指导客户断电等待两分钟后再尝试，仍然无法打开，于是安排工程师当晚加急上门。工程师检查发现门锁开关的感应片损坏，更换门锁开关后门能正常打开。洗衣机在保修期内，配件和人工均免费，加急上门也没有另外收费。",
        "工单 WX1016-18：客户反映电饭煲煮饭时不跳保温，米饭底部焦糊。客服判断为温控器故障，电饭煲属于小家电，按保修政策采用寄修方式，客服为客户安排了上门取件，并告知维修周期约七天。客户询问维修期间能否先换一台，客服说明寄修产品不提供备用机，但如果检测确认是质量问题，可以直接换新，客户表示同意寄修。",
        "工单 WX1017-19：客户反映空调室内机往下滴水，把墙面和地板都弄湿了。工程师上门发现冷凝水排水管被灰尘和絮状物堵塞，水从接水盘溢出。工程师疏通了排水管并清洗了接水盘，试机半小时没有再滴水。该问题属于日常维护范畴，考虑到空调刚过保修期一个月，经网点主管同意，本次不收取费用，并建议客户每年开机前清洗一次。",
        "工单 WX1017-20：客户反映新买的冰箱夜里噪音很大，影响睡眠，怀疑是质量问题。工程师上门用分贝仪检测，运行噪音在产品标称范围内，但冰箱背面距离墙面太近，散热不畅导致压缩机频繁启动。工程师帮客户把冰箱往外挪了十厘米并调整了底脚，噪音有所降低。客户仍然觉得声音偏大，工程师登记了客户意见，告知如果一周后仍不满意可以申请质量检测。",
        "工单 WX1018-21：客户来电反映燃气热水器显示故障代码 E4，没有热水。客服查询代码含义为点火失败，询问后得知客户家前一天刚做过燃气管道检修，判断可能是燃气表前的阀门没有完全打开。客服指导客户检查后确认阀门只开了一半，打开后热水器恢复正常，本工单电话解决。",
        "工单 WX1018-22：客户反映无线吸尘器充满电后只能用五分钟，购买时宣传的续航是四十分钟。工程师检测确认电池容量衰减到原来的三成左右，吸尘器已使用两年半，电池的保修期为一年，需要付费更换。新电池加人工共二百八十元，客户对价格犹豫后同意更换，换新后测试续航恢复到三十五分钟以上。",
    ]
    intro = "售后维修中心十月第二周工单汇总。本周共处理上门、电话和远程工单二十二张，其中免费处理十四张，收费处理六张，客户放弃维修一张，待客户确认一张；涉及客户投诉三起，分别与收费标准、配件价格和上门迟到有关。以下按工单号顺序列出处理经过。"
    outro = "本周小结：一是安装环节的遗漏仍然是上门问题的重要来源，洗衣机运输螺栓未拆、洗碗机排水管弯折都属于此类，建议安装完成后增加当面检查确认；二是收费类工单的争议集中在客户对收费标准不了解，建议在预约阶段就把可能产生的费用告知客户；三是上门迟到的投诉说明派单系统对前一单超时缺少预警，需要调度组优化。下周将重点回访本周的三起投诉工单。"
    return intro + "".join(orders) + outro


def night_shift_summary() -> str:
    """夜班通话纪要汇总：由十一通电话摘要组成的长文（超过 3,000 字）。"""
    calls = [
        "二十二点零五分，客户来电反映外卖送错，收到的是别人点的麻辣香锅，自己点的是清淡的粥和小菜，家里有病人只能吃清淡的。客服联系骑手核实，确认是骑手在同一栋楼取错了袋子。客服为客户安排了重新配送，并全额退还首单费用，另外发放一张二十元的红包作为补偿，客户表示接受。骑手所属站点被记录一次错送。",
        "二十二点二十分，客户来电反映生鲜订单少送了一盒牛奶和两斤苹果，订单显示已全部送达。客服请客户在订单页面上传收货照片，核实后确认是拣货遗漏，客服为客户办理了少送商品的退款，共四十二元，同时询问客户是否需要补送，客户表示第二天早上还要用牛奶，客服安排了次日早上七点前补送。",
        "二十二点四十分，客户来电称通过平台预订的酒店到店后被告知没有房间，客户带着两个孩子，时间已经很晚。客服联系酒店，酒店承认超售，客服为客户在附近三公里内协调了一家同等级酒店，差价由平台承担，并安排了网约车送客户过去。客户情绪逐渐平复，但要求追究原酒店的责任，客服已提交商家违规处理。",
        "二十二点五十五分，客户反映用积分兑换一张二十元的话费券，积分已经扣除，但券没有到账。客服查询发现兑换时券库存刚好用完，系统扣了积分却没有发券。客服为客户退回了两千积分，并手动补发了一张同面额的话费券，客户确认收到后表示满意。",
        "二十三点十分，客户来电询问为什么收到了异地登录提醒，担心账号被盗。客服核实登录记录，发现确实有一次来自外省的登录尝试，但因为没有通过验证码校验而失败。客服指导客户修改了登录密码，开启了登录保护，并提醒客户不要把验证码告诉任何人，客户表示放心了。",
        "二十三点三十五分，客户反映给手机充值一百元，付款成功但话费一直没有到账。客服查询到充值订单处于运营商处理中，因为运营商系统夜间维护导致延迟。客服告知客户维护结束后会自动到账，最晚明早八点，如未到账会自动退款，客户同意等待。",
        "二十三点五十分，客户来电想把周六的游乐园门票改到周日，但页面显示门票不支持改期。客服查询后确认该门票的规则是使用日前一天可以免费退票，于是指导客户先退掉周六的门票，再重新购买周日的门票，两张票价格相同，客户没有产生额外费用。",
        "零点零五分，客户反映在小区的电动车充电桩扫码充电，充了两个小时，却被扣了八个小时的费用。客服查看充电记录，发现充电桩在电池充满后没有自动断电，一直计费到客户拔下插头。客服为客户退还了多扣的六元，并把这台充电桩的情况反馈给设备运维团队排查。",
        "零点二十分，客户反映共享单车已经还车，但系统一直在计费，显示骑行了三个小时。客服查看车辆定位，确认车辆已停在规定区域，是还车时锁没有落实。客服为客户结束了订单，退还了多扣的费用，并提醒客户以后还车后确认 App 显示还车成功。",
        "零点五十五分，客户来电称乘坐网约车时把笔记本电脑落在了后座。客服联系司机，司机确认电脑在车上，但已经在返回郊区的路上。客服与双方协商，由司机第二天上午送回，客户承担往返费用，客服为客户争取了一半的优惠，客户表示感谢。",
        "一点零五分，客户反映外卖送到时汤洒了一半，包装袋里都是汤汁，没法吃。客户提供了照片，客服确认属于配送途中洒漏，为客户全额退款，并把商家包装密封不足的问题反馈给商家运营，建议汤类餐品使用带密封盖的餐盒。",
        "一点三十分，客户来电对机票改签费用提出异议，客户因航班延误错过了转机，改签时被收取了三百元改签费。客服核实后确认首段航班延误是航空公司原因，按照规定转机改签应当免费，客服向航空公司提交了免费改签申请，并承诺三个工作日内退还已收取的费用。",
        "一点五十分，客户来电想取消明天上午的家政保洁预约，因为临时要出差，页面显示取消需要收取三十元违约金。客服核实到预约时间距离现在还有八个多小时，按照规则提前四小时以上取消可以免收违约金，是页面计算有误，客服为客户免费取消了预约，并把计算问题提交给技术团队。",
        "两点十分，客户反映快递柜的取件码提示已失效，无法取出包裹。客服查询发现包裹因超时滞留已经被快递员取回网点，客服联系网点安排第二天重新投递，并免除了超时保管费，客户希望以后包裹快要超时时能提前提醒，客服记录了这条建议。",
        "两点四十分，客户来电询问电子钱包提现为什么还没到账，提现申请已经提交了三个小时。客服查询到提现处于银行处理中，夜间提现由银行批量处理，一般在次日上午十点前到账，客服把预计时间告知客户，并说明如果超过二十四小时没有到账可以再次来电，客户表示理解。",
        "三点整，客户来电称视频会员在同一天被扣了两次费用。客服核实发现客户在两个不同的入口分别开通了自动续费，导致重复扣费。客服为客户关闭了其中一个自动续费，并退还了重复扣除的二十五元，同时说明了以后如何在一个地方统一管理续费。",
        "三点三十分，客户来电称家里老人突然发烧，在平台下单购买了退烧药，但配送时间显示要一个小时，希望能加急。客服联系附近的二十四小时药店确认有货，帮客户把订单转给距离更近的药店并加急配送，最终二十分钟送达，客户连声感谢。",
        "三点五十分，客户来电称预订的机场接机服务，司机在航班落地前就打电话催促，说等不了要走。客户的航班因天气原因延误了一个半小时，客服联系司机说明情况，司机同意继续等待，客服同时为司机申请了延误等待补贴，避免类似情况再次发生，客户顺利接上了车。",
        "四点十五分，客户投诉外卖骑手态度恶劣，因为客户在电话里提醒骑手送餐超时，骑手在送达时出言不逊。客服向客户道歉，记录了投诉内容，并联系骑手所属站点核实，站点表示会对骑手进行批评教育，客服为客户发放了十元红包，客户表示希望平台能真正处理，而不是只发红包。",
        "四点四十分，客户投诉网约车司机绕路，平时三十元左右的路程这次收了五十二元。客服查看行程轨迹，确认司机没有按照导航推荐路线行驶，多绕了约八公里。客服为客户退还了多收的二十二元，并对司机进行了扣分处理。五点十分，客户反映在商场停车场出场时扫码缴费，被扣了两次停车费。客服核实后确认是缴费成功后道闸没有及时抬杆，客户又扫了一次码，系统重复收费，客服为客户退还了重复扣除的十五元。",
        "五点二十五分，客户反映拒收了一个快递包裹，但订单的退款一直没有到账。客服查询到包裹已经在退回商家的途中，按照规则商家签收后才会退款，预计需要三天。客户表示等不了这么久，客服核实客户信用良好，为客户办理了先行退款，退款在十分钟内到账。",
        "五点四十分，客户来电称预订的早餐地址填错了，送到了公司而不是家里。客服联系商家，早餐还没有出餐，商家同意修改配送地址，配送费差额由客户承担两元，客户表示可以，问题解决。",
    ]
    intro = "客服中心十月七日夜班通话纪要汇总。本班次从二十二点到次日六点，共接听来电二十三通，涉及外卖、生鲜、酒店、门票、账号安全、积分、充值、电子钱包、共享出行、网约车、机票、接送机、家政、快递、药品配送、停车和会员等业务，全部当班处理完毕或已转交相关部门跟进。以下按时间顺序记录每一通电话的处理经过。"
    outro = "班次小结：本班次的问题集中在第三方服务环节，外卖错送和洒漏、生鲜少送、酒店超售、骑手态度、网约车绕路等问题都需要相关业务线加强对合作方的管理；充电桩和停车道闸的重复计费说明设备异常时缺少自动纠错；运营商夜间维护导致的充值延迟，建议在充值页面提前提示；快递柜超时取回和视频会员重复扣费都暴露出提醒机制的不足。以上问题已整理成日报，提交给各业务线负责人。涉及退款和补偿的工单都已当班处理完成，只有机票改签费用需要航空公司在三个工作日内退还；涉及系统问题的充电桩计费、停车道闸、积分兑换库存和家政违约金计算四项已提交技术团队，将在白班交接会上逐项确认处理进度。"
    return intro + "".join(calls) + outro


def long_texts() -> list[str]:
    texts = [
        LETTER_DELIVERY,
        REFUND_DISPUTE,
        MEMBERSHIP_RENEWAL,
        repair_weekly(),
        INVOICE_ISSUE,
        ACCOUNT_APPEAL,
        POINTS_CLEARED,
        night_shift_summary(),
        SUGGESTIONS,
        BROADBAND,
    ]
    for text in texts:
        assert "\n" not in text, "每篇长文必须写在一行里"
        assert 400 <= len(text) <= 6000, len(text)
    assert sum(1 for text in texts if len(text) > 3000) >= 2
    return texts


# ---------------------------------------------------------------- 极简 xlsx 写入器

def column_letter(index: int) -> str:
    """0 → A，25 → Z，26 → AA。"""
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def xml_text(value: str) -> str:
    cleaned = "".join(ch for ch in value if ch in "\t\n\r" or ord(ch) >= 0x20)
    return cleaned.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def excel_serial(moment: datetime) -> float:
    delta = moment - datetime(1899, 12, 30)
    return delta.days + delta.seconds / 86400


def display_width(value: object) -> int:
    text = value.strftime("%Y-%m-%d %H:%M") if isinstance(value, datetime) else str(value)
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)


STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="yyyy-mm-dd hh:mm"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Microsoft YaHei"/></font><font><b/><sz val="11"/><name val="Microsoft YaHei"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFEEF2F6"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="4">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>
"""

STYLE_HEADER, STYLE_DATETIME, STYLE_WRAP = 1, 2, 3


class SharedStrings:
    def __init__(self) -> None:
        self.index: dict[str, int] = {}
        self.items: list[str] = []
        self.count = 0

    def add(self, text: str) -> int:
        self.count += 1
        if text not in self.index:
            self.index[text] = len(self.items)
            self.items.append(text)
        return self.index[text]

    def xml(self) -> str:
        parts = []
        for text in self.items:
            space = ' xml:space="preserve"' if text != text.strip() or "\n" in text else ""
            parts.append(f"<si><t{space}>{xml_text(text)}</t></si>")
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{self.count}" '
            f'uniqueCount="{len(self.items)}">' + "".join(parts) + "</sst>"
        )


def sheet_xml(rows: list[list[object]], strings: SharedStrings, *, selected: bool, wrap_columns: set[int]) -> str:
    width = max(len(row) for row in rows)
    widths = [10] * width
    body = []
    for r, row in enumerate(rows, start=1):
        cells = []
        for c, value in enumerate(row):
            if value is None or value == "":
                continue
            ref = f"{column_letter(c)}{r}"
            widths[c] = min(60, max(widths[c], display_width(value) + 2))
            if r == 1:
                cells.append(f'<c r="{ref}" t="s" s="{STYLE_HEADER}"><v>{strings.add(str(value))}</v></c>')
            elif isinstance(value, datetime):
                cells.append(f'<c r="{ref}" s="{STYLE_DATETIME}"><v>{excel_serial(value)!r}</v></c>')
            elif isinstance(value, bool):
                cells.append(f'<c r="{ref}" t="b"><v>{int(value)}</v></c>')
            elif isinstance(value, int | float):
                cells.append(f'<c r="{ref}"><v>{value!r}</v></c>')
            else:
                style = f' s="{STYLE_WRAP}"' if c in wrap_columns else ""
                cells.append(f'<c r="{ref}" t="s"{style}><v>{strings.add(str(value))}</v></c>')
        body.append(f'<row r="{r}">' + "".join(cells) + "</row>")
    cols = "".join(
        f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths)
    )
    tab = ' tabSelected="1"' if selected else ""
    dimension = f"A1:{column_letter(width - 1)}{len(rows)}"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<dimension ref="{dimension}"/>'
        f'<sheetViews><sheetView{tab} workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/></sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="16"/>'
        f"<cols>{cols}</cols>"
        "<sheetData>" + "".join(body) + "</sheetData>"
        '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
        "</worksheet>"
    )


def write_xlsx(path: Path, sheets: list[tuple[str, list[list[object]], set[int]]]) -> None:
    strings = SharedStrings()
    sheet_parts = [
        sheet_xml(rows, strings, selected=(i == 0), wrap_columns=wrap) for i, (_name, rows, wrap) in enumerate(sheets)
    ]
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + "".join(
            f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(len(sheets))
        )
        + '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/xl/sharedStrings.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
        'Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
        'Target="docProps/app.xml"/>'
        "</Relationships>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<bookViews><workbookView activeTab="0"/></bookViews><sheets>'
        + "".join(
            f'<sheet name="{xml_text(name)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
            for i, (name, _rows, _wrap) in enumerate(sheets)
        )
        + "</sheets></workbook>"
    )
    n = len(sheets)
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{i + 1}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{i + 1}.xml"/>'
            for i in range(n)
        )
        + f'<Relationship Id="rId{n + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        f'<Relationship Id="rId{n + 2}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" '
        'Target="sharedStrings.xml"/>'
        "</Relationships>"
    )
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:title>文枢示例数据</dc:title><dc:creator>WenShu</dc:creator>"
        '<dcterms:created xsi:type="dcterms:W3CDTF">2026-10-21T00:00:00Z</dcterms:created>'
        '<dcterms:modified xsi:type="dcterms:W3CDTF">2026-10-21T00:00:00Z</dcterms:modified>'
        "</cp:coreProperties>"
    )
    app = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>WenShu samples</Application></Properties>"
    )
    parts: list[tuple[str, str]] = [
        ("[Content_Types].xml", content_types),
        ("_rels/.rels", root_rels),
        ("docProps/core.xml", core),
        ("docProps/app.xml", app),
        ("xl/workbook.xml", workbook),
        ("xl/_rels/workbook.xml.rels", workbook_rels),
        ("xl/styles.xml", STYLES_XML),
    ]
    parts += [(f"xl/worksheets/sheet{i + 1}.xml", xml) for i, xml in enumerate(sheet_parts)]
    parts.append(("xl/sharedStrings.xml", strings.xml()))  # 最后生成：上面的工作表都已登记完字符串

    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in parts:
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 21, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, text.encode("utf-8"))
    path.write_bytes(buffer.getvalue())


# ---------------------------------------------------------------- 生成


def notes_sheet(rows: list[list[object]]) -> tuple[str, list[list[object]], set[int]]:
    return ("说明", rows, {1})


def make_xlsx_sample() -> None:
    rng = random.Random(20261021)
    rows = dialogue_rows(rng, unique=112, duplicates=6, blanks=2, start=datetime(2026, 9, 15, 8, 0))
    notes = [
        ["项目", "说明"],
        ["数据", "虚构的客服对话，每行一条用户问题，可以直接用于意图识别"],
        ["推荐列", "用户问题（文枢会按平均字数自动推荐这一列）"],
        ["意图类别", "内置提示词的示例类别：咨询、办理、投诉、建议、其他"],
        ["特殊行", "包含少量重复问题（相同文本只调用一次）和 2 行空问题（自动跳过）"],
    ]
    write_xlsx(XLSX_SAMPLE, [("对话", rows, {1}), notes_sheet(notes)])
    print(f"{XLSX_SAMPLE.relative_to(ROOT)}：{len(rows) - 1} 行")


def make_csv_sample() -> None:
    rng = random.Random(20261022)
    rows = dialogue_rows(rng, unique=95, duplicates=4, blanks=1, start=datetime(2026, 9, 16, 9, 0))
    header = rows[0] + ["客户等级"]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(header)
    for index, row in enumerate(rows[1:]):
        session_id, text, moment, channel = row
        if index == 7:
            text = "你好，我上周买的吹风机用了两次就不出热风了。\n能不能直接换一台新的？"
        writer.writerow([session_id, text, moment.strftime("%Y-%m-%d %H:%M:%S"), channel, rng.choice(LEVELS)])
    CSV_SAMPLE.write_bytes(out.getvalue().encode("utf-8-sig"))
    print(f"{CSV_SAMPLE.relative_to(ROOT)}：{len(rows) - 1} 行")


def make_txt_sample() -> None:
    texts = long_texts()
    TXT_SAMPLE.write_text("\n".join(texts) + "\n", encoding="utf-8")
    lengths = "、".join(f"{len(t):,}" for t in texts)
    print(f"{TXT_SAMPLE.relative_to(ROOT)}：{len(texts)} 篇，字数 {lengths}")


def make_e2e_fixture() -> None:
    """docs/08 第 10.2 节：工作表“对话”201 行（表头 + 200 行），约 10% 重复，3 行为空；另有工作表“说明”5 行。"""
    rng = random.Random(200)
    rows = dialogue_rows(rng, unique=177, duplicates=20, blanks=3, start=datetime(2026, 9, 15, 8, 0))
    assert len(rows) == 201, len(rows)
    assert sum(1 for row in rows[1:] if row[1] == "") == 3
    notes = [
        ["项目", "说明"],
        ["用途", "文枢端到端测试（场景 A：意图识别主流程）"],
        ["结构", "工作表“对话”：表头 + 200 行，列为会话ID、用户问题、时间、渠道"],
        ["覆盖", "咨询、办理、投诉、建议、其他 5 类，约 10% 重复，3 行为空"],
        ["生成", "samples/make_samples.py，内容固定，可重复生成"],
    ]
    write_xlsx(E2E_FIXTURE, [("对话", rows, {1}), notes_sheet(notes)])
    print(f"{E2E_FIXTURE.relative_to(ROOT)}：{len(rows) - 1} 行")


def main() -> None:
    make_xlsx_sample()
    make_csv_sample()
    make_txt_sample()
    make_e2e_fixture()


if __name__ == "__main__":
    main()
