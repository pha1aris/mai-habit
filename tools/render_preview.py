from PIL import Image, ImageDraw, ImageFont
import math
from pathlib import Path

# McDonald's brand colors
RED = "#DA291C"
YELLOW = "#FFC72C"
GOLD = "#D97706"
DARK_GOLD = "#B45309"
INK = "#1A1513"
MUTED = "#5C4F47"
LIGHT_MUTED = "#8C7B70"
LINE = "#E5D8CC"
BG_TOP = "#FFF9F0"
CARD_BG = "#FFFFFF"
REJECT_BG = "#FFF8F0"
REJECT_LINE = "#F8D4A8"
GREEN_TAG = "#15803D"
GREEN_BG = "#DCFCE7"

FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
FONT_REG = "C:/Windows/Fonts/msyh.ttc"

def font(path, size):
    return ImageFont.truetype(path, size, index=0)

def draw_checkmark(d, cx, cy, size=12, color=GREEN_TAG):
    """Draw a crisp vector checkmark."""
    # (cx, cy) is top-left approx
    p1 = (cx, cy + size * 0.5)
    p2 = (cx + size * 0.35, cy + size * 0.9)
    p3 = (cx + size * 0.9, cy + size * 0.1)
    d.line([p1, p2], fill=color, width=max(2, int(size * 0.2)))
    d.line([p2, p3], fill=color, width=max(2, int(size * 0.2)))

def draw_pill_badge(d, x, y, text, font_obj, bg_color, text_color):
    """Draw a clean pill badge with a manually drawn vector checkmark."""
    bbox = font_obj.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    
    pad_h = 10
    check_size = 11
    pad_v = 4
    bw = pad_h + check_size + 6 + tw + pad_h
    bh = max(th + pad_v * 2, 26)
    
    # Pill bg
    d.rounded_rectangle([x, y, x + bw, y + bh], radius=bh//2, fill=bg_color)
    # Checkmark
    check_y = y + (bh - check_size) // 2 - 1
    draw_checkmark(d, x + pad_h, check_y, size=check_size, color=text_color)
    # Text
    d.text((x + pad_h + check_size + 6, y + (bh - th) // 2 - 2), text, font=font_obj, fill=text_color)
    return bw

def draw_cute_burger(d, cx, cy, scale=1.0):
    """Draw an adorable McDonald's style burger with cute face."""
    s = scale
    # Bun Top
    d.pieslice([cx - int(56*s), cy - int(48*s), cx + int(56*s), cy + int(10*s)],
               start=180, end=360, fill="#F6C851")
    # Bun top outline highlight
    d.arc([cx - int(56*s), cy - int(48*s), cx + int(56*s), cy + int(10*s)],
          start=195, end=345, fill="#FDE68A", width=max(1, int(2*s)))

    # Sesame seeds
    seeds = [(-22, -26), (-8, -34), (8, -32), (24, -24), (-12, -18), (12, -18)]
    for sx, sy in seeds:
        d.ellipse([cx + int(sx*s)-3, cy + int(sy*s)-2, cx + int(sx*s)+3, cy + int(sy*s)+2], fill="#E5AA30")
    
    # Cute eyes on top bun!
    # Left eye
    d.ellipse([cx - int(16*s), cy - int(16*s), cx - int(8*s), cy - int(8*s)], fill="#2B1A0E")
    d.ellipse([cx - int(14*s), cy - int(15*s), cx - int(10*s), cy - int(11*s)], fill="#FFFFFF")
    # Right eye
    d.ellipse([cx + int(8*s), cy - int(16*s), cx + int(16*s), cy - int(8*s)], fill="#2B1A0E")
    d.ellipse([cx + int(10*s), cy - int(15*s), cx + int(14*s), cy - int(11*s)], fill="#FFFFFF")
    # Cute blushing cheeks
    d.ellipse([cx - int(26*s), cy - int(10*s), cx - int(17*s), cy - int(4*s)], fill="#F87171")
    d.ellipse([cx + int(17*s), cy - int(10*s), cx + int(26*s), cy - int(4*s)], fill="#F87171")
    # Happy smile
    d.arc([cx - int(6*s), cy - int(13*s), cx + int(6*s), cy - int(5*s)], start=0, end=180, fill="#2B1A0E", width=max(2, int(2*s)))

    # Lettuce layer (wavy green)
    d.ellipse([cx - int(62*s), cy - int(8*s), cx + int(62*s), cy + int(10*s)], fill="#4ADE80")

    # Beef / Chicken Patty (savory brown)
    d.rounded_rectangle([cx - int(56*s), cy + int(2*s), cx + int(56*s), cy + int(18*s)],
                        radius=int(6*s), fill="#78350F")

    # Melted Cheese (golden yellow corners hanging down)
    cheese_pts = [
        (cx - int(52*s), cy + int(16*s)),
        (cx - int(15*s), cy + int(16*s)),
        (cx - int(25*s), cy + int(27*s)),
        (cx + int(5*s), cy + int(16*s)),
        (cx + int(30*s), cy + int(25*s)),
        (cx + int(52*s), cy + int(16*s)),
        (cx + int(48*s), cy + int(12*s)),
        (cx - int(48*s), cy + int(12*s)),
    ]
    d.polygon(cheese_pts, fill="#FBBF24")

    # Bun Bottom
    d.rounded_rectangle([cx - int(54*s), cy + int(18*s), cx + int(54*s), cy + int(36*s)],
                        radius=int(10*s), fill="#F6C851")

def draw_cute_fries(d, cx, cy, scale=1.0):
    """Draw adorable McDonald's red fries carton with golden fries."""
    s = scale
    # Golden fries poking out top
    fries = [
        (-22, -45, -14, 0),
        (-12, -58, -4, 0),
        (-2, -65, 6, 0),
        (8, -52, 16, 0),
        (18, -42, 26, 0),
        (-18, -50, -10, 0),
        (2, -55, 10, 0),
    ]
    for fx1, fy1, fx2, fy2 in fries:
        d.rounded_rectangle([cx + int(fx1*s), cy + int(fy1*s), cx + int(fx2*s), cy + int(fy2*s)],
                            radius=int(2*s), fill="#FBBF24", outline="#D97706", width=1)

    # Red Carton
    carton_pts = [
        (cx - int(26*s), cy - int(10*s)),
        (cx + int(26*s), cy - int(10*s)),
        (cx + int(20*s), cy + int(36*s)),
        (cx - int(20*s), cy + int(36*s)),
    ]
    d.polygon(carton_pts, fill=RED)

    # Golden Arch "M" on box
    d.arc([cx - int(14*s), cy + int(2*s), cx - int(2*s), cy + int(22*s)], start=180, end=360, fill="#FFC72C", width=max(2, int(3*s)))
    d.arc([cx - int(2*s), cy + int(2*s), cx + int(10*s), cy + int(22*s)], start=180, end=360, fill="#FFC72C", width=max(2, int(3*s)))

    # Cute eyes on fries carton
    d.ellipse([cx - int(9*s), cy + int(14*s), cx - int(5*s), cy + int(18*s)], fill="#FFFFFF")
    d.ellipse([cx + int(5*s), cy + int(14*s), cx + int(9*s), cy + int(18*s)], fill="#FFFFFF")
    d.arc([cx - int(3*s), cy + int(18*s), cx + int(3*s), cy + int(24*s)], start=0, end=180, fill="#FFFFFF", width=max(1, int(2*s)))

def draw_speech_bubble(d, x, y, text, font_obj, bg_color="#FFFFFF", text_color=RED, border_color="#F8D4A8"):
    """Draw a cute comic speech bubble."""
    bbox = font_obj.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    bw = tw + 20
    bh = th + 12
    d.rounded_rectangle([x, y, x + bw, y + bh], radius=8, fill=bg_color, outline=border_color, width=1)
    # Triangle tail pointing down-right
    d.polygon([(x + bw - 14, y + bh), (x + bw - 6, y + bh), (x + bw - 4, y + bh + 8)], fill=bg_color)
    d.line([(x + bw - 14, y + bh), (x + bw - 4, y + bh + 8)], fill=border_color, width=1)
    d.line([(x + bw - 4, y + bh + 8), (x + bw - 6, y + bh)], fill=border_color, width=1)
    d.text((x + 10, y + 5), text, font=font_obj, fill=text_color)

def draw_star_bullet(d, cx, cy, r=5, color=GOLD):
    """Draw a cute star icon."""
    points = []
    for i in range(10):
        angle = math.pi * i / 5 - math.pi / 2
        radius = r if i % 2 == 0 else r * 0.45
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    d.polygon(points, fill=color)

def render_social_preview(output_path):
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(img)

    # Subtle warm gradient background
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t * 0.03))
        g = int(249 * (1 - t * 0.03))
        b = int(240 * (1 - t * 0.05))
        d.line([(0, y), (W, y)], fill=(r, g, b))

    # Left McDonald's Red accent bar
    d.rectangle([0, 0, 10, H], fill=RED)

    # Golden arches warm background curves top right
    d.ellipse([W - 350, -200, W + 120, 280], fill="#FFF0D0")
    d.ellipse([W - 190, 90, W + 90, 370], fill="#FFE8C0")

    # Speech bubble above illustrations
    draw_speech_bubble(d, W - 230, 24, "俩汉堡顶饱！", font(FONT_BOLD, 15), bg_color="#FFFFFF", text_color=RED)

    # Cute burger and fries placed cleanly to the right
    draw_cute_burger(d, W - 110, 125, scale=1.12)
    draw_cute_fries(d, W - 200, 155, scale=1.0)

    x = 64

    # 1. Category Tag + Hook
    tag_text = "【麦门点单嘴替】 麦懂你"
    tag_font = font(FONT_BOLD, 16)
    tb = tag_font.getbbox(tag_text)
    tag_w = tb[2] - tb[0] + 28
    d.rounded_rectangle([x, 38, x + tag_w, 70], radius=8, fill="#FDECEA")
    d.text((x + 14, 44), tag_text, font=tag_font, fill=RED)

    desc_x = x + tag_w + 18
    d.text((desc_x, 45), "拒绝套餐硬塞可乐 ｜ 随心配吃不饱救星 ｜ 券后真实算底价",
           font=font(FONT_REG, 16), fill=MUTED)

    # 2. Main Hero Headline — adjusted font size so it NEVER collides with illustration
    d.text((x, 86), "就想单点俩汉堡，不想被套餐硬塞可乐？",
           font=font(FONT_BOLD, 42), fill=INK)
    d.text((x, 148), "你的麦门吃法说一次，每次秒出最划算方案！",
           font=font(FONT_BOLD, 40), fill=RED)

    # 3. Sub-copy / Habit Scenario
    d.text((x, 230),
           "比如你的固定吃法：『纯鸡肉 · 必须吃俩堡 · 不喝含糖汽水 · 预算28元』",
           font=font(FONT_BOLD, 21), fill=INK)
    d.text((x, 268),
           "死守口味底线 → 调真实算价接口比对卡包优惠 → 没推荐的套餐明明白白交底",
           font=font(FONT_REG, 19), fill=MUTED)

    # Thin separator line
    d.line([(x, 314), (W - x, 314)], fill=LINE, width=1)

    # === CARD 1: Recommendation (Left) ===
    c1_l, c1_t, c1_r, c1_b = x, 328, x + 610, 524
    d.rounded_rectangle([c1_l, c1_t, c1_r, c1_b], radius=14, fill=CARD_BG, outline="#E2D6CA", width=2)
    d.rounded_rectangle([c1_l, c1_t + 2, c1_l + 7, c1_b - 2], radius=4, fill=RED)

    # Header in Card 1
    d.rounded_rectangle([c1_l + 20, c1_t + 16, c1_l + 138, c1_t + 44], radius=6, fill=RED)
    d.text((c1_l + 26, c1_t + 20), "麦门精选搭子", font=font(FONT_BOLD, 15), fill="#FFFFFF")
    d.text((c1_l + 150, c1_t + 21), "纯鸡肉 · 不吃辣 · 顶饱双堡", font=font(FONT_REG, 15), fill=MUTED)

    # Price right
    price_val = "¥23.50"
    p_font = font(FONT_BOLD, 36)
    pb = p_font.getbbox(price_val)
    pw = pb[2] - pb[0]
    d.text((c1_r - 20 - pw, c1_t + 10), price_val, font=p_font, fill=RED)
    d.text((c1_r - 20 - pw - 68, c1_t + 22), "券后实付", font=font(FONT_REG, 14), fill=MUTED)

    # Combo Item Title
    d.text((c1_l + 20, c1_t + 58), "板烧鸡腿堡 ＋ 经典吉士汉堡", font=font(FONT_BOLD, 27), fill=INK)

    # Sub details
    d.text((c1_l + 20, c1_t + 104), "28元预算还剩 ¥4.50 ｜ 调用实时接口试算底价，绝非标价机械硬凑",
           font=font(FONT_REG, 15), fill=LIGHT_MUTED)

    # Green checkmark pill tags (vector drawn checkmark)
    tag_y = c1_t + 142
    badge_f = font(FONT_BOLD, 13)
    curr_bx = c1_l + 20
    for tag in ["纯鸡肉", "顶饱双堡", "零饮料", "28元预算内"]:
        w = draw_pill_badge(d, curr_bx, tag_y, tag, badge_f, GREEN_BG, GREEN_TAG)
        curr_bx += w + 10

    # === CARD 2: Transparent Exclusions (Right) ===
    c2_l, c2_t, c2_r, c2_b = x + 630, 328, W - x, 524
    d.rounded_rectangle([c2_l, c2_t, c2_r, c2_b], radius=14, fill=REJECT_BG, outline=REJECT_LINE, width=1)
    d.rounded_rectangle([c2_l, c2_t + 2, c2_l + 6, c2_b - 2], radius=4, fill=GOLD)

    # Card 2 header badge
    d.rounded_rectangle([c2_l + 18, c2_t + 16, c2_l + 242, c2_t + 44], radius=6, fill="#FEF3C7")
    d.text((c2_l + 26, c2_t + 20), "为什么没推荐别的？（绝不踩坑）", font=font(FONT_BOLD, 14), fill=DARK_GOLD)

    reasons = [
        ("经典三件套", "默认捆绑大杯可乐薯条，坚决不硬塞"),
        ("板烧双堡套", "用券后实付仍需 ¥29.5，超出今日28元限额"),
        ("随心配 1+1", "单汉堡吃不饱，强搭红茶小食不合习惯"),
    ]
    ry = c2_t + 58
    for rtitle, rdesc in reasons:
        draw_star_bullet(d, c2_l + 24, ry + 10, r=5, color=GOLD)
        d.text((c2_l + 34, ry), f"{rtitle}：", font=font(FONT_BOLD, 15), fill="#78350F")
        rt_w = font(FONT_BOLD, 15).getbbox(f"{rtitle}：")[2] - font(FONT_BOLD, 15).getbbox(f"{rtitle}：")[0]
        d.text((c2_l + 34 + rt_w, ry), rdesc, font=font(FONT_REG, 15), fill="#92400E")
        ry += 32

    # Footer
    d.line([(x, 552), (W - x, 552)], fill=LINE, width=1)
    d.text((x, 574), "麦懂你 · 懂你的麦门吃法 (mai-habit)", font=font(FONT_BOLD, 17), fill=INK)
    
    # Vector star in footer
    draw_star_bullet(d, x + 316, 584, r=6, color=GOLD)
    d.text((x + 328, 576), "手机免安装直接试玩：pha1aris.github.io/mai-habit/", font=font(FONT_REG, 15), fill=MUTED)
    d.text((W - x - 220, 576), "GitHub 开源: pha1aris/mai-habit", font=font(FONT_REG, 15), fill=MUTED)

    img.save(output_path, optimize=True)
    print(f"Social preview saved to: {output_path}")

def render_readme_banner(output_path):
    """Render a dedicated horizontal banner specifically for GitHub README header."""
    W, H = 1000, 360
    img = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(img)

    for y in range(H):
        t = y / H
        r = int(255 * (1 - t * 0.03))
        g = int(249 * (1 - t * 0.03))
        b = int(240 * (1 - t * 0.05))
        d.line([(0, y), (W, y)], fill=(r, g, b))

    # Outer border
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=16, outline="#E8DDD5", width=2)
    d.rounded_rectangle([0, 0, 10, H], radius=4, fill=RED)

    # Soft golden decorative background curves
    d.ellipse([W - 270, -120, W + 60, 220], fill="#FFF0D0")
    d.ellipse([W - 130, 120, W + 60, 320], fill="#FFE8C0")

    # Speech bubble above illustrations
    draw_speech_bubble(d, W - 180, 16, "俩汉堡顶饱！", font(FONT_BOLD, 13), bg_color="#FFFFFF", text_color=RED)

    # Cute burger and fries cleanly positioned
    draw_cute_burger(d, W - 80, 95, scale=0.88)
    draw_cute_fries(d, W - 150, 120, scale=0.8)

    x = 44

    # Category badge
    tag_text = "【麦门点单嘴替】 麦懂你 · mai-habit"
    tag_font = font(FONT_BOLD, 14)
    tb = tag_font.getbbox(tag_text)
    tag_w = tb[2] - tb[0] + 24
    d.rounded_rectangle([x, 26, x + tag_w, 54], radius=6, fill="#FDECEA")
    d.text((x + 12, 31), tag_text, font=tag_font, fill=RED)

    d.text((x + tag_w + 14, 32), "拒绝套餐硬塞可乐 ｜ 随心配吃不饱救星 ｜ 券后真实算底价",
           font=font(FONT_REG, 14), fill=MUTED)

    # Main Headline
    d.text((x, 68), "就想单点俩汉堡，不想被套餐硬塞可乐？",
           font=font(FONT_BOLD, 33), fill=INK)
    d.text((x, 116), "你的麦门吃法说一次，每次秒出最划算方案！",
           font=font(FONT_BOLD, 31), fill=RED)

    # Sub-copy
    d.text((x, 172),
           "比如你的固定吃法：『纯鸡肉 · 必须吃俩堡 · 不喝含糖汽水 · 预算28元』",
           font=font(FONT_BOLD, 16), fill=INK)
    d.text((x, 202),
           "死守口味底线 → 调实时接口比对卡包优惠算实付 → 没推荐的套餐明明白白交底",
           font=font(FONT_REG, 15), fill=MUTED)

    # Mini cards row at bottom
    # Card A: Result
    ca_l, ca_t, ca_r, ca_b = x, 246, x + 440, 324
    d.rounded_rectangle([ca_l, ca_t, ca_r, ca_b], radius=10, fill="#FFFFFF", outline="#E2D6CA", width=1)
    d.rounded_rectangle([ca_l, ca_t + 1, ca_l + 5, ca_b - 1], radius=3, fill=RED)
    d.text((ca_l + 14, ca_t + 10), "今日精选搭子", font=font(FONT_BOLD, 13), fill=RED)
    d.text((ca_l + 100, ca_t + 10), "板烧鸡腿堡 ＋ 经典吉士汉堡", font=font(FONT_BOLD, 14), fill=INK)
    d.text((ca_r - 80, ca_t + 8), "¥23.50", font=font(FONT_BOLD, 22), fill=RED)
    
    # Checkmark pill tags in card A
    badge_f = font(FONT_BOLD, 11)
    bx = ca_l + 12
    by = ca_t + 40
    for tag in ["纯鸡肉", "俩汉堡", "零饮料", "剩¥4.50"]:
        w = draw_pill_badge(d, bx, by, tag, badge_f, GREEN_BG, GREEN_TAG)
        bx += w + 6

    # Card B: Rejection reason
    cb_l, cb_t, cb_r, cb_b = x + 456, 246, W - 44, 324
    d.rounded_rectangle([cb_l, cb_t, cb_r, cb_b], radius=10, fill=REJECT_BG, outline=REJECT_LINE, width=1)
    d.rounded_rectangle([cb_l, cb_t + 1, cb_l + 5, cb_b - 1], radius=3, fill=GOLD)
    d.text((cb_l + 14, cb_t + 10), "为什么没推常规套餐？（透明交底）", font=font(FONT_BOLD, 13), fill=DARK_GOLD)
    d.text((cb_l + 14, cb_t + 32), "• 经典套餐：默认硬塞可乐薯条，坚决不买", font=font(FONT_REG, 13), fill="#78350F")
    d.text((cb_l + 14, cb_t + 52), "• 板烧双堡套：用券后实付 ¥29.5 超出预算", font=font(FONT_REG, 13), fill="#78350F")

    img.save(output_path, optimize=True)
    print(f"Readme banner saved to: {output_path}")

if __name__ == "__main__":
    out_dir = Path("C:/Users/phalaris/Documents/Codex/2026-10-24/zui/outputs/mai-habit/docs")
    render_social_preview(str(out_dir / "social-preview.png"))
    render_readme_banner(str(out_dir / "hero-banner.png"))
    # Also save to scratch
    scratch_dir = Path("C:/Users/phalaris/.gemini/antigravity-ide/brain/9ee231c5-16f8-4de1-8c8a-ecf565b1486d/scratch")
    render_social_preview(str(scratch_dir / "preview_v6.png"))
    render_readme_banner(str(scratch_dir / "hero_banner_v6.png"))
