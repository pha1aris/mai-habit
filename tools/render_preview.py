from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
RED = "#DA291C"
YELLOW = "#FFC72C"
GOLD = "#D97706"
INK = "#1F2328"
MUTED = "#57606A"
LIGHT_MUTED = "#6E7781"
LINE = "#D8DEE4"
BG = "#FFFFFF"
SOFT = "#F6F8FA"
REJECT_BG = "#FFFBF6"
REJECT_LINE = "#F4D7B5"

FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
FONT_REG = "C:/Windows/Fonts/msyh.ttc"

def font(path, size):
    return ImageFont.truetype(path, size, index=0)

def render(output_path):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Left McDonald's Red accent bar
    d.rectangle([0, 0, 10, H], fill=RED)

    # Decorative background circles (warm golden yellow & soft warm red)
    d.ellipse([W - 270, -150, W + 90, 210], fill="#FFF9E6")
    d.ellipse([W - 140, 130, W + 80, 350], fill="#FDECEA")

    x = 76

    # 1. Top Category Tag & Hook
    d.rounded_rectangle([x, 44, x + 248, 76], radius=6, fill="#FDECEA")
    d.text((x + 14, 50), "【麦门点单嘴替】 麦懂你", font=font(FONT_BOLD, 16), fill=RED)
    d.text((x + 266, 50), "拒绝套餐硬塞可乐 ｜ 随心配吃不饱救星 ｜ 券后真实算底价", font=font(FONT_REG, 17), fill=MUTED)

    # 2. Main Headline
    d.text((x, 92), "就想单点俩汉堡，不想被套餐硬塞可乐？", font=font(FONT_BOLD, 48), fill=INK)
    d.text((x, 160), "你的麦门吃法说一次，每次秒出最划算点单方案！", font=font(FONT_BOLD, 48), fill=RED)

    # 3. Subtitle / Scenario
    d.text((x, 248), "比如你的固定习惯：『纯鸡肉 · 必须吃俩堡 · 不喝含糖汽水 · 预算28元』", font=font(FONT_BOLD, 22), fill=INK)
    d.text((x, 284), "死守你的口味底线 → 自动比对卡包优惠算实付 → 没推荐的套餐明明白白交底", font=font(FONT_REG, 21), fill=MUTED)

    # 4. Bottom Cards:
    c1_left, c1_top, c1_right, c1_bottom = x, 344, x + 610, 526
    d.rounded_rectangle([c1_left, c1_top, c1_right, c1_bottom], radius=14, fill=SOFT, outline=LINE, width=2)
    d.rounded_rectangle([c1_left, c1_top + 2, c1_left + 6, c1_bottom - 2], radius=4, fill=RED)

    # Card 1 Badge & tags
    d.rounded_rectangle([c1_left + 22, c1_top + 18, c1_left + 140, c1_top + 46], radius=6, fill=RED)
    d.text((c1_left + 28, c1_top + 22), "麦门精选搭子", font=font(FONT_BOLD, 15), fill="#FFFFFF")
    d.text((c1_left + 152, c1_top + 23), "纯鸡肉 · 不吃辣 · 顶饱双堡", font=font(FONT_REG, 16), fill=MUTED)

    # Card 1 Price area
    price_str = "¥23.50"
    p_font = font(FONT_BOLD, 33)
    p_box = p_font.getbbox(price_str)
    p_w = p_box[2] - p_box[0]
    d.text((c1_right - 22 - p_w, c1_top + 16), price_str, font=p_font, fill=RED)
    d.text((c1_right - 22 - p_w - 74, c1_top + 24), "券后实付", font=font(FONT_REG, 15), fill=MUTED)

    # Card 1 Dish name
    d.text((c1_left + 22, c1_top + 64), "板烧鸡腿堡 ＋ 经典吉士汉堡", font=font(FONT_BOLD, 28), fill=INK)

    # Card 1 Bottom Details
    d.text((c1_left + 22, c1_top + 114), "28元预算还剩 ¥4.50 ｜ 调用真实试算接口算底价，绝非标价硬凑", font=font(FONT_REG, 15), fill=LIGHT_MUTED)

    # Card 2: Exclusion transparent reasons
    c2_left, c2_top, c2_right, c2_bottom = x + 636, 344, W - 76, 526
    d.rounded_rectangle([c2_left, c2_top, c2_right, c2_bottom], radius=14, fill=REJECT_BG, outline=REJECT_LINE, width=1)
    d.rounded_rectangle([c2_left, c2_top + 2, c2_left + 6, c2_bottom - 2], radius=4, fill=GOLD)

    d.rounded_rectangle([c2_left + 22, c2_top + 18, c2_left + 244, c2_top + 46], radius=6, fill="#FEF3C7")
    d.text((c2_left + 30, c2_top + 22), "为什么没推荐别的？（绝不踩坑）", font=font(FONT_BOLD, 14), fill="#92400E")

    d.text((c2_left + 22, c2_top + 58), "• 经典套餐：默认捆绑大杯可乐与薯条，不硬塞", font=font(FONT_REG, 15), fill="#78350F")
    d.text((c2_left + 22, c2_top + 88), "• 板烧双堡套：用券后实付仍需 ¥29.5，超出今日限额", font=font(FONT_REG, 15), fill="#78350F")
    d.text((c2_left + 22, c2_top + 118), "• 随心配 1+1：单汉堡吃不饱，强搭小食不合习惯", font=font(FONT_REG, 15), fill="#78350F")

    # 5. Footer
    d.line([x, 558, W - 76, 558], fill=LINE, width=1)
    d.text((x, 578), "麦懂你 · 懂你的麦门吃法 (mai-habit)", font=font(FONT_BOLD, 17), fill=INK)
    d.text((x + 320, 580), "手机免安装直接试玩：pha1aris.github.io/mai-habit/", font=font(FONT_REG, 15), fill=MUTED)
    d.text((W - 76 - 220, 580), "GitHub 开源: pha1aris/mai-habit", font=font(FONT_REG, 15), fill=MUTED)

    img.save(output_path, optimize=True)
    print("Saved preview to:", output_path)

if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "preview_final.png"
    render(out)
