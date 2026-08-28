# -*- coding: utf-8 -*-
"""
tavern-android / main.py —— 酒馆版手机端（Kivy）。
聊天 + 互动小说 + 世界书管理 + 设置，全部复用 ai_core 纯内核。
打包：buildozer android debug（见 README + GitHub Actions）。
"""
import os
import re
import sys
import time
import traceback
import threading

from kivy.app import App
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.utils import escape_markup
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.gridlayout import GridLayout
from kivy.uix.spinner import Spinner
from kivy.uix.checkbox import CheckBox
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.metrics import dp, sp
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.properties import ListProperty
from kivy.uix.widget import Widget

import ai_core


# Kivy/SDL2_ttf 不会稳定地从 MuMu 或真机系统字体回退到中文字体。
# 将 SIL OFL 许可的 CJK 与 emoji 矢量字体随 APK 打包，并按字形分段渲染。
_FONT_NAME = 'NotoSansCJKsc'
_FONT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'assets',
    'NotoSansCJKsc-Regular.otf',
)
_EMOJI_FONT_NAME = 'NotoEmoji'
_EMOJI_FONT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'assets',
    'NotoEmoji-Regular.ttf',
)
_SYMBOLS2_FONT_NAME = 'NotoSansSymbols2'
_SYMBOLS2_FONT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'assets',
    'NotoSansSymbols2-Regular.ttf',
)
_SYMBOLS_FONT_NAME = 'NotoSansSymbols'
_SYMBOLS_FONT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'assets',
    'NotoSansSymbols-Regular.ttf',
)
_FONT_AVAILABLE = False
_EMOJI_FONT_AVAILABLE = False
_SYMBOLS2_FONT_AVAILABLE = False
_SYMBOLS_FONT_AVAILABLE = False
try:
    if os.path.isfile(_FONT_PATH):
        LabelBase.register(name=_FONT_NAME, fn_regular=_FONT_PATH)
        _FONT_AVAILABLE = True
except Exception as e:
    print('中文字体加载失败，回退到 Kivy 默认字体:', e)
try:
    if os.path.isfile(_EMOJI_FONT_PATH):
        LabelBase.register(name=_EMOJI_FONT_NAME, fn_regular=_EMOJI_FONT_PATH)
        _EMOJI_FONT_AVAILABLE = True
except Exception as e:
    print('emoji 字体加载失败，回退到主字体:', e)
try:
    if os.path.isfile(_SYMBOLS2_FONT_PATH):
        LabelBase.register(name=_SYMBOLS2_FONT_NAME, fn_regular=_SYMBOLS2_FONT_PATH)
        _SYMBOLS2_FONT_AVAILABLE = True
except Exception as e:
    print('Symbols2 字体加载失败，回退到主字体:', e)
try:
    if os.path.isfile(_SYMBOLS_FONT_PATH):
        LabelBase.register(name=_SYMBOLS_FONT_NAME, fn_regular=_SYMBOLS_FONT_PATH)
        _SYMBOLS_FONT_AVAILABLE = True
except Exception as e:
    print('Symbols 字体加载失败，回退到主字体:', e)

_UI_FONT_NAME = _FONT_NAME if _FONT_AVAILABLE else 'Roboto'

_EMOJI_MARKUP_AVAILABLE = (
    _EMOJI_FONT_AVAILABLE or _SYMBOLS2_FONT_AVAILABLE or _SYMBOLS_FONT_AVAILABLE
)
_EMOJI_FALLBACK_FONTS = {
    '🗑': _SYMBOLS2_FONT_NAME,
    '⚙️': _SYMBOLS_FONT_NAME,
}

_EMOJI_RUN_RE = re.compile(
    r'([\U0001F000-\U0001FAFF\u2300-\u23FF\u2600-\u27BF\u2B00-\u2BFF'
    r'\u200D\u20E3\uFE0F\U000E0020-\U000E007F]+)'
)


def _emoji_markup(text):
    """Wrap emoji runs in the bundled emoji font, with a safe plain-text fallback."""
    text = '' if text is None else str(text)
    if not _EMOJI_MARKUP_AVAILABLE:
        return text
    escaped = escape_markup(text)

    def wrap(match):
        value = match.group(0)
        fallback_name = _EMOJI_FALLBACK_FONTS.get(value)
        if fallback_name == _SYMBOLS2_FONT_NAME and _SYMBOLS2_FONT_AVAILABLE:
            font_name = fallback_name
        elif fallback_name == _SYMBOLS_FONT_NAME and _SYMBOLS_FONT_AVAILABLE:
            font_name = fallback_name
        elif _EMOJI_FONT_AVAILABLE:
            font_name = _EMOJI_FONT_NAME
        else:
            return value
        return '[font=%s]%s[/font]' % (font_name, value)

    return _EMOJI_RUN_RE.sub(wrap, escaped)


if _FONT_AVAILABLE:
    Builder.load_string("""
<Label>:
    font_name: 'NotoSansCJKsc'
<Button>:
    font_name: 'NotoSansCJKsc'
<TextInput>:
    font_name: 'NotoSansCJKsc'
<Spinner>:
    font_name: 'NotoSansCJKsc'
<Popup>:
    title_font: 'NotoSansCJKsc'
""")

# 主题色：Material 3 风格的柔和紫蓝色，所有页面共用同一组 token。
PRIMARY = (0.32, 0.25, 0.82, 1.0)
PRIMARY_DARK = (0.24, 0.18, 0.64, 1.0)
PRIMARY_SOFT = (0.91, 0.89, 1.0, 1.0)
BLUE = PRIMARY  # 保留旧名称，避免影响核心交互代码。
AI_BG = (0.985, 0.98, 1.0, 1.0)
USER_BG = PRIMARY
TEXT_DARK = (0.12, 0.10, 0.18, 1.0)
TEXT_WHITE = (1, 1, 1, 1)
BG = (0.965, 0.955, 0.98, 1.0)
CARD = (1, 1, 1, 1)
FIELD_BG = (0.965, 0.96, 0.985, 1.0)
MUTED = (0.42, 0.40, 0.50, 1.0)
DIVIDER = (0.88, 0.86, 0.92, 1.0)
SUCCESS = (0.14, 0.55, 0.38, 1.0)
DANGER = (0.78, 0.20, 0.28, 1.0)
Window.clearcolor = BG


# --------------------------------------------------------------------------- #
# 崩溃兜底：Android 无控制台，未捕获异常会直接闪退且不留痕。
# 这里把异常写进磁盘文件，并弹窗提示，避免静默崩溃、便于定位。
# --------------------------------------------------------------------------- #
def _crash_log_path():
    try:
        base = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        base = '.'
    return os.path.join(base, 'crash.log')


def _write_crash(typ, value, tb):
    try:
        with open(_crash_log_path(), 'a', encoding='utf-8') as f:
            f.write('\n=== %s ===\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
            f.write(''.join(traceback.format_exception(typ, value, tb)))
    except Exception:
        pass


def _guard(fn):
    """装饰器：捕获方法内的未处理异常并弹窗，避免 Android 静默闪退。"""
    def _wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as ex:
            import traceback as _tb
            show_error(fn.__name__, ''.join(_tb.format_exception_only(type(ex), ex))[:240])
    return _wrapper





def install_crash_handler():
    """捕获未处理异常，写崩溃日志并尝试弹窗（不阻断程序）。"""
    original = sys.excepthook

    def hook(typ, value, tb):
        msg = ''.join(traceback.format_exception(typ, value, tb))
        try:
            _write_crash(typ, value, tb)
        except Exception:
            pass
        print(msg)
        # 用可滚动弹窗展示完整 traceback，让用户能看懂/截图，而不是闪退
        try:
            from kivy.uix.scrollview import ScrollView
            box = BoxLayout(orientation='vertical', padding=(dp(14), dp(12)),
                            spacing=dp(8))
            box.add_widget(_label('运行出错（已记录到 crash.log）',
                                  color=DANGER, bold=True, font_size=sp(13),
                                  size_hint_y=None, height=dp(28)))
            sv = ScrollView(size_hint=(1, 1))
            sv.add_widget(_label(msg, font_size=sp(10), color=TEXT_DARK))
            box.add_widget(sv)
            close = ModernButton(text='关闭', background_color=FIELD_BG,
                                color=TEXT_DARK, font_size=sp(13))
            pop = Popup(title='错误', title_font=_UI_FONT_NAME, content=box,
                        size_hint=(0.92, 0.7))
            close.bind(on_release=lambda *_: pop.dismiss())
            box.add_widget(close)
            pop.open()
        except Exception:
            pass
        return None

    sys.excepthook = hook
    # Python 3.8+：子线程未捕获异常不走 sys.excepthook，必须单独接住，
    # 否则 daemon 线程（如发送/生成所在的 Thread）崩溃会直接杀进程 → 闪退。
    try:
        threading.excepthook = lambda args: hook(
            args.exc_type, args.exc_value, args.exc_traceback)
    except Exception:
        pass


def show_error(title, text):
    """主动弹出一个非致命错误提示（用于已知风险点的兜底）。"""
    try:
        from kivy.uix.popup import Popup
        box = BoxLayout(orientation='vertical', padding=(dp(14), dp(12)),
                        spacing=dp(8))
        box.add_widget(_label(text, font_size=sp(12), color=DANGER))
        close = ModernButton(text='关闭', background_color=FIELD_BG,
                            color=TEXT_DARK, font_size=sp(13))
        pop = Popup(title=title, title_font=_UI_FONT_NAME, content=box,
                    size_hint=(0.9, 0.5))
        close.bind(on_release=lambda *_: pop.dismiss())
        box.add_widget(close)
        pop.open()
    except Exception:
        pass



def _shade(color, amount=0.08):
    """Lighten/darken an RGBA color for pressed and disabled states."""
    r, g, b, a = color
    return (max(0, min(1, r - amount)), max(0, min(1, g - amount)),
            max(0, min(1, b - amount)), a)


def _label(text='', **kwargs):
    """Create a consistently configured label without changing dynamic text."""
    kwargs.setdefault('font_name', _UI_FONT_NAME)
    kwargs.setdefault('color', TEXT_DARK)
    kwargs.setdefault('font_size', sp(14))
    kwargs.setdefault('halign', 'left')
    kwargs.setdefault('valign', 'middle')
    label = Label(text=text, **kwargs)
    label.bind(size=lambda w, _: setattr(w, 'text_size', (w.width, None)))
    return label


def _section_header(title, subtitle=''):
    box = BoxLayout(orientation='vertical', size_hint_y=None,
                    height=dp(52) if subtitle else dp(32), spacing=dp(2))
    box.add_widget(_label(title, bold=True, font_size=sp(16),
                          size_hint_y=None, height=dp(26)))
    if subtitle:
        box.add_widget(_label(subtitle, color=MUTED, font_size=sp(12),
                              size_hint_y=None, height=dp(22)))
    return box


class Divider(Widget):
    def __init__(self, **kwargs):
        kwargs.setdefault('size_hint_y', None)
        kwargs.setdefault('height', dp(1))
        super().__init__(**kwargs)
        with self.canvas:
            self._color = Color(rgba=DIVIDER)
            self._line = Line(points=[self.x, self.y, self.right, self.y],
                              width=1)
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *_):
        self._line.points = [self.x, self.y, self.right, self.y]


class SurfaceBox(BoxLayout):
    """Rounded surface used for cards, toolbars, dialogs and the composer."""

    surface_color = ListProperty(CARD)
    border_color = ListProperty((0, 0, 0, 0))
    surface_radius = ListProperty([dp(16)] * 4)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            self._surface_color = Color(rgba=self.surface_color)
            self._surface_rect = RoundedRectangle(
                pos=self.pos, size=self.size,
                radius=[(dp(16), dp(16))] * 4)
            self._surface_border_color = Color(rgba=self.border_color)
            self._surface_border = Line(rounded_rectangle=(
                self.x, self.y, self.width, self.height, dp(16)), width=0.8)
        self.bind(pos=self._sync_surface, size=self._sync_surface,
                  surface_color=self._sync_surface,
                  border_color=self._sync_surface,
                  surface_radius=self._sync_surface)
        self._sync_surface()

    def _sync_surface(self, *_):
        self._surface_color.rgba = self.surface_color
        self._surface_rect.pos = self.pos
        self._surface_rect.size = self.size
        self._surface_rect.radius = [(r, r) for r in self.surface_radius]
        self._surface_border_color.rgba = self.border_color
        radius = self.surface_radius[0] if self.surface_radius else dp(16)
        self._surface_border.rounded_rectangle = (
            self.x, self.y, self.width, self.height, radius)


class ModernButton(Button):
    """Flat rounded button with a predictable pressed state on Android."""

    fill_color = ListProperty(CARD)
    pressed_color = ListProperty((0.88, 0.86, 0.96, 1.0))
    disabled_fill_color = ListProperty((0.88, 0.87, 0.91, 1.0))
    button_radius = ListProperty([dp(13)] * 4)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fill_color = list(self.background_color)
        self.pressed_color = _shade(self.fill_color, -0.05)
        # Button's own rectangle is square; the visible background is our rounded layer.
        self.background_color = (0, 0, 0, 0)
        self.background_normal = ''
        self.background_down = ''
        self.background_disabled = ''
        with self.canvas.before:
            self._button_color = Color(rgba=self.fill_color)
            self._button_rect = RoundedRectangle(
                pos=self.pos, size=self.size,
                radius=[(dp(13), dp(13))] * 4)
        self.bind(pos=self._sync_button, size=self._sync_button,
                  fill_color=self._sync_button,
                  pressed_color=self._sync_button,
                  disabled_fill_color=self._sync_button,
                  button_radius=self._sync_button,
                  state=self._sync_button,
                  disabled=self._sync_button)
        self._sync_button()

    def _sync_button(self, *_):
        if self.disabled:
            color = self.disabled_fill_color
        elif self.state == 'down':
            color = self.pressed_color
        else:
            color = self.fill_color
        self._button_color.rgba = color
        self._button_rect.pos = self.pos
        self._button_rect.size = self.size
        self._button_rect.radius = [(r, r) for r in self.button_radius]


class ModernTextInput(TextInput):
    """Stable text field: keep Kivy's native text layer visible on Android."""

    def __init__(self, **kwargs):
        # 统一保证所有页面的输入文字都与浅色输入底有足够对比度。
        kwargs.setdefault('foreground_color', TEXT_DARK)
        kwargs.setdefault('hint_text_color', MUTED)
        kwargs.setdefault('selection_color', (0.18, 0.43, 1.0, 0.25))
        kwargs.setdefault('background_color', CARD)
        kwargs.setdefault('font_size', sp(14))
        # Kivy 2.3.1 defaults to input_type='null', which disables Android
        # IME composition. Explicit text mode is required for Chinese input.
        kwargs.setdefault('input_type', 'text')
        kwargs.setdefault('cursor_color', PRIMARY)
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_active = ''
        self.background_disabled_normal = ''
        self.background_disabled_down = ''
        self.disabled_foreground_color = TEXT_DARK
        self.padding = list(self.padding or [dp(12), dp(10)])


class AvatarBadge(Label):
    """Small circular identity badge used by the chat and page chrome."""

    fill_color = ListProperty(PRIMARY)

    def __init__(self, **kwargs):
        kwargs.setdefault('size_hint', (None, None))
        kwargs.setdefault('size', (dp(32), dp(32)))
        kwargs.setdefault('font_name', _UI_FONT_NAME)
        kwargs.setdefault('font_size', sp(12))
        kwargs.setdefault('bold', True)
        kwargs.setdefault('color', TEXT_WHITE)
        kwargs.setdefault('halign', 'center')
        kwargs.setdefault('valign', 'middle')
        super().__init__(**kwargs)
        self.text_size = self.size
        with self.canvas.before:
            self._avatar_color = Color(rgba=self.fill_color)
            self._avatar = RoundedRectangle(pos=self.pos, size=self.size,
                                            radius=[(dp(16), dp(16))] * 4)
        self.bind(pos=self._sync_avatar, size=self._sync_avatar,
                  fill_color=self._sync_avatar)

    def _sync_avatar(self, *_):
        self.text_size = self.size
        self._avatar_color.rgba = self.fill_color
        self._avatar.pos = self.pos
        self._avatar.size = self.size
        self._avatar.radius = [(min(self.width, self.height) / 2,
                                min(self.width, self.height) / 2)] * 4


class BubbleButton(ModernButton):
    """聊天气泡：长按（≥0.5s）触发菜单。不 disabled（disabled 会吞掉触摸事件）。"""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.long_press_cb = None
        self._press_at = None
        self._button_rect.radius = [(dp(18), dp(18))] * 4

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._press_at = time.time()
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos) and self._press_at is not None:
            dt = time.time() - self._press_at
            self._press_at = None
            if dt >= 0.5 and self.long_press_cb:
                self.long_press_cb()
                return True
        return super().on_touch_up(touch)


def _bubble(text, is_user):
    """生成一条聊天气泡（BubbleButton 充当圆角气泡，长按弹操作菜单）。"""
    raw_text = '' if text is None else str(text)
    btn = BubbleButton(
        text=_emoji_markup(raw_text),
        markup=_EMOJI_MARKUP_AVAILABLE,
        # Keep the reading column narrower than the screen so this is a chat
        # bubble, not another full-width content card.
        size_hint_x=0.74 if is_user else 0.84,
        size_hint_y=None,
        # NumericProperty 不接受 None；先给气泡一个最小高度，随后按文本高度调整。
        height=dp(44),
        halign='left',
        valign='middle',
        text_size=(None, None),
        # AI replies read like a story column; only the user's own text gets a
        # filled bubble. This prevents a long reply becoming a giant white card.
        background_color=USER_BG if is_user else (0, 0, 0, 0),
        color=TEXT_WHITE if is_user else TEXT_DARK,
        padding=(dp(15), dp(10)),
        font_size=sp(15),
        line_height=1.2,
    )

    def update_bubble_width(widget, _):
        widget.text_size = (max(dp(90), widget.width - dp(28)), None)

    btn.bind(width=update_bubble_width)
    # Clock.schedule_once 只传入 dt；宽度绑定则传入 (widget, value)，两者分开适配。
    Clock.schedule_once(lambda _dt: update_bubble_width(btn, _dt), 0)

    def update_bubble_height(widget, _):
        text_height = widget.texture_size[1] or 0
        widget.height = max(dp(48), text_height + dp(24))

    btn.bind(texture_size=update_bubble_height)
    btn.raw_text = raw_text
    return btn


def _set_bubble_text(widget, text):
    """Set display text while keeping the original text for editing and persistence."""
    widget.raw_text = '' if text is None else str(text)
    widget.text = _emoji_markup(widget.raw_text)


class ChatScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.hm = None          # ai_core.HistoryManager
        self.busy = False
        self.cur_bubble = None  # 流式中正在更新的气泡
        self._reasoning_parts = []  # 本回合思维链片段（工作线程收集，主线程展示）
        self.build_ui()

    # ---------- UI ----------
    def build_ui(self):
        # Full-bleed reading surface. The toolbar, option tray and composer are
        # overlays, leaving the conversation with the whole viewport.
        root = FloatLayout()

        self.scroll = ScrollView(size_hint=(1, 0.88), pos_hint={'x': 0, 'y': 0},
                                 bar_width=dp(3), bar_color=PRIMARY,
                                 bar_inactive_color=DIVIDER,
                                 scroll_type=['bars', 'content'])
        self.msg_box = BoxLayout(orientation='vertical', size_hint_y=None,
                                 spacing=dp(5),
                                 # ScrollView itself has no padding property in
                                 # Kivy 2.3; keep the overlay clearance on the
                                 # viewport child instead.
                                 padding=(dp(16), dp(82), dp(16), dp(78)))
        self.msg_box.bind(minimum_height=self.msg_box.setter('height'))
        self.scroll.add_widget(self.msg_box)
        root.add_widget(self.scroll)

        # Compact welcome state; it is removed entirely once a message exists.
        self.empty_state = BoxLayout(orientation='vertical', size_hint_y=None,
                                     height=dp(158), padding=(dp(10), dp(12)),
                                     spacing=dp(5))
        welcome_avatar = AvatarBadge(text='酒', size=(dp(42), dp(42)),
                                     fill_color=PRIMARY)
        avatar_holder = AnchorLayout(size_hint_y=None, height=dp(42))
        avatar_holder.add_widget(welcome_avatar)
        self.empty_state.add_widget(avatar_holder)
        self.empty_state.add_widget(_label(_emoji_markup('✨ 开始一段新的故事'),
                                           markup=_EMOJI_MARKUP_AVAILABLE,
                                           bold=True, font_size=sp(17),
                                           size_hint_y=None, height=dp(32),
                                           halign='center'))
        self.empty_state.add_widget(_label('发送一句话，或开启小说模式开始互动。\n对话会自动保存在本机。',
                                           color=MUTED, font_size=sp(12),
                                           halign='center', valign='top',
                                           size_hint_y=None, height=dp(48)))

        # This tray is collapsed and transparent until real choices exist.
        self.choices_panel = SurfaceBox(orientation='vertical', size_hint_y=None,
                                        size_hint_x=0.92, height=0,
                                        pos_hint={'x': 0.04, 'y': 0.105},
                                        opacity=0, padding=(dp(12), dp(8)),
                                        spacing=dp(5), surface_color=CARD,
                                        border_color=(0, 0, 0, 0),
                                        surface_radius=[dp(18)] * 4)
        self.choices_box = BoxLayout(orientation='vertical', size_hint_y=None,
                                     spacing=dp(6))
        self.choices_box.bind(minimum_height=self.choices_box.setter('height'))
        self.choices_panel.add_widget(self.choices_box)
        root.add_widget(self.choices_panel)

        # Floating composer, visually separated from the message stream.
        bottom = SurfaceBox(size_hint=(0.92, None), height=dp(58),
                            pos_hint={'x': 0.04, 'y': 0.015},
                            padding=(dp(6), dp(6)), spacing=dp(8),
                            surface_color=CARD, border_color=(0, 0, 0, 0),
                            surface_radius=[dp(20)] * 4)
        self.input = ModernTextInput(hint_text='说点什么…', multiline=False,
                               size_hint_x=1, background_color=FIELD_BG,
                               background_normal='', background_active='',
                               hint_text_color=MUTED, foreground_color=TEXT_DARK,
                               padding=(dp(14), dp(9)))
        self.input.bind(on_text_validate=lambda *_: self.send())
        bottom.add_widget(self.input)
        self.send_btn = ModernButton(text='发送',
                                     size_hint_x=None, width=dp(68),
                                     background_color=PRIMARY, color=TEXT_WHITE,
                                     font_size=sp(13), button_radius=[dp(16)] * 4)
        self.send_btn.bind(on_release=lambda *_: self.send())
        bottom.add_widget(self.send_btn)
        root.add_widget(bottom)

        # Lightweight top app bar; no more giant rounded header card.
        top = BoxLayout(orientation='horizontal', size_hint=(1, None), height=dp(70),
                        pos_hint={'x': 0, 'top': 1}, padding=(dp(18), dp(11)),
                        spacing=dp(9))
        top.add_widget(AvatarBadge(text='酒', fill_color=PRIMARY))
        heading = BoxLayout(orientation='vertical', spacing=dp(0), size_hint_x=1)
        self.title_lbl = _label(_emoji_markup('酒馆'), markup=_EMOJI_MARKUP_AVAILABLE,
                                bold=True, font_size=sp(18),
                                size_hint_y=None, height=dp(28))
        self.subtitle_lbl = _label('准备好继续你的故事', color=MUTED, font_size=sp(11),
                                   size_hint_y=None, height=dp(19))
        heading.add_widget(self.title_lbl)
        heading.add_widget(self.subtitle_lbl)
        top.add_widget(heading)
        actions = BoxLayout(size_hint_x=None, width=dp(180), spacing=dp(6))
        self.tavern_btn = ModernButton(
            text='小说模式', size_hint_x=None, width=dp(68), height=dp(34),
            background_color=PRIMARY_SOFT, color=PRIMARY_DARK, font_size=sp(11),
            button_radius=[dp(17)] * 4)
        self.tavern_btn.bind(on_release=lambda *_: self.toggle_tavern())
        actions.add_widget(self.tavern_btn)
        regen_btn = ModernButton(text='重试', size_hint_x=None, width=dp(42),
                                 height=dp(34), background_color=FIELD_BG,
                                 color=TEXT_DARK, font_size=sp(11),
                                 button_radius=[dp(17)] * 4)
        regen_btn.bind(on_release=lambda *_: self.regen())
        actions.add_widget(regen_btn)
        new_btn = ModernButton(text='新对话', size_hint_x=None, width=dp(58),
                               height=dp(34), background_color=FIELD_BG,
                               color=TEXT_DARK, font_size=sp(11),
                               button_radius=[dp(17)] * 4)
        new_btn.bind(on_release=lambda *_: self.new_chat())
        actions.add_widget(new_btn)
        top.add_widget(actions)
        root.add_widget(top)
        self.add_widget(root)

    # ---------- 启动 ----------
    def on_enter(self):
        if self.hm is None:
            self.hm = ai_core.HistoryManager()
            self.load_history()
            self.refresh_tavern_btn()
        self._refresh_header()

    def load_history(self):
        self.msg_box.clear_widgets()
        for m in self.hm.current():
            if m.get('role') in ('user', 'assistant'):
                self.add_bubble(m.get('content') or '', m['role'] == 'user')
        self._update_empty_state()

    def _refresh_header(self):
        if not self.hm:
            return
        pet_name = (self.hm.cfg.get('pet_name') or '酒馆').strip()
        self.title_lbl.text = _emoji_markup(pet_name)
        self.subtitle_lbl.text = '小说模式已开启' if self.hm.cfg.get('tavern_mode') else '准备好继续你的故事'

    def _update_empty_state(self):
        has_messages = any(m.get('role') in ('user', 'assistant') for m in self.hm.current()) if self.hm else False
        if has_messages:
            if self.empty_state.parent is self.msg_box:
                self.msg_box.remove_widget(self.empty_state)
        elif self.empty_state.parent is None:
            self.msg_box.add_widget(self.empty_state)

    # ---------- 气泡 ----------
    def add_bubble(self, text, is_user):
        if self.empty_state.parent is self.msg_box:
            self.msg_box.remove_widget(self.empty_state)
        b = _bubble(text, is_user)
        row = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(3),
                        padding=(0, dp(4)))
        row.bind(minimum_height=row.setter('height'))

        meta = AnchorLayout(size_hint_y=None, height=dp(23),
                            anchor_x='right' if is_user else 'left')
        meta_copy = BoxLayout(size_hint_x=None, width=dp(92), spacing=dp(5))
        badge = AvatarBadge(text='我' if is_user else '酒', size=(dp(23), dp(23)),
                            fill_color=PRIMARY if is_user else (0.22, 0.18, 0.38, 1))
        meta_copy.add_widget(badge)
        meta_copy.add_widget(_label('我' if is_user else '酒馆', color=MUTED,
                                    font_size=sp(10), bold=True))
        meta.add_widget(meta_copy)
        row.add_widget(meta)

        bubble_holder = AnchorLayout(size_hint_y=None, height=b.height,
                                     anchor_x='right' if is_user else 'left',
                                     anchor_y='top')
        bubble_holder.add_widget(b)
        row.add_widget(bubble_holder)
        b.chat_row = row
        b.bind(height=lambda widget, value: setattr(bubble_holder, 'height', value))
        b.long_press_cb = lambda: self.show_bubble_menu(b, is_user)
        self.msg_box.add_widget(row)
        self.scroll_to_bottom()
        return b

    def rebuild_bubbles(self):
        """清空并重画当前页全部气泡（编辑/删除/重新生成后调用）。"""
        self.msg_box.clear_widgets()
        self.choices_box.clear_widgets()
        self.choices_box.height = 0
        self._hide_choices()
        self.load_history()

    def scroll_to_bottom(self):
        # Kivy BoxLayout.children 按倒序存放，children[-1] 是最老消息。
        # 直接设为 0 表示 ScrollView 底部，避免发送后跳回历史开头。
        Clock.schedule_once(lambda *_: setattr(self.scroll, 'scroll_y', 0), 0.05)

    # ---------- 发送 ----------
    def send(self):
        if self.busy or not self.hm:
            return
        text = (self.input.text or '').strip()
        if not text:
            return
        self.input.text = ''
        self.add_bubble(text, True)
        self.busy = True
        self.set_input_enabled(False)
        self.subtitle_lbl.text = '正在思考…'
        t = threading.Thread(target=self._run, args=(text,), daemon=True)
        t.start()

    def set_input_enabled(self, enabled):
        self.input.disabled = not enabled
        # Keep the composer surface white while a request is running. The
        # disabled state still blocks duplicate input without leaving a gray box.
        self.input.opacity = 1.0
        if hasattr(self, 'send_btn'):
            self.send_btn.disabled = not enabled
            self.send_btn.text = '发送' if enabled else '生成中…'

    def _run(self, text, append_user=True):
        try:
            if append_user:
                self.hm.append_user(text)
            if self.hm.cfg.get('tavern_mode'):
                text = '> ' + text
            msgs = self.hm.build_context()
            self.cur_bubble = None
            self._reasoning_parts = []

            def on_token(tok):
                Clock.schedule_once(lambda *_: self.append_stream(tok), 0)

            def on_reasoning(r):
                if r:
                    self._reasoning_parts.append(r)

            ai_text, reasoning, usage = ai_core.run_model_session(
                msgs, self.hm.cfg, on_token=on_token, on_reasoning=on_reasoning)
            if reasoning:
                self._reasoning_parts.append(reasoning)
            # 流式结束后收尾
            Clock.schedule_once(lambda *_: self.on_finished(ai_text, usage), 0)
        except Exception as e:
            err = '⚠️ 出错了: %s' % e
            Clock.schedule_once(lambda *_: self.add_bubble(err, False), 0)
            Clock.schedule_once(lambda *_: self.on_finished('', None), 0)

    def append_stream(self, tok):
        if self.cur_bubble is None:
            self.cur_bubble = self.add_bubble('', False)
        _set_bubble_text(self.cur_bubble, self.cur_bubble.raw_text + tok)

    def on_finished(self, ai_text, usage):
        self.busy = False
        self.set_input_enabled(True)
        self._refresh_header()
        # 若流式已渲染则回写完整文本（保证与存档一致）
        if self.cur_bubble is not None:
            _set_bubble_text(self.cur_bubble, ai_text or self.cur_bubble.raw_text)
        else:
            self.add_bubble(ai_text or '(空回复)', False)
        self.cur_bubble = None
        self.hm.append_assistant(ai_text)
        # 思维链简化展示：灰色小字追加在 AI 气泡下方（便于观察 AI 是否入戏）
        self._render_reasoning()
        if usage:
            stats = ai_core.load_token_stats()
            for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                stats[k] = int(stats.get(k, 0)) + int(usage.get(k, 0) or 0)
            stats['turns'] = int(stats.get('turns', 0)) + 1
            ai_core.save_token_stats(stats)
        # 小说模式：解析选项
        if self.hm.cfg.get('tavern_mode'):
            self.render_choices(ai_text)
        # 分页：达到上限自动翻页（后台）
        if len([m for m in self.hm.current() if m.get('role')]) >= ai_core.PAGE_SIZE:
            threading.Thread(target=self._rollover_bg, daemon=True).start()

    def _render_reasoning(self):
        """把本回合思维链渲染成气泡下方的灰色小字（有才显示）。"""
        parts = [p for p in self._reasoning_parts if (p or '').strip()]
        self._reasoning_parts = []
        if not parts:
            return
        rtext = '\n'.join(parts).strip()
        if not rtext:
            return
        tip = Label(text=_emoji_markup('💭 ' + rtext), markup=_EMOJI_MARKUP_AVAILABLE,
                    font_size=sp(11), color=MUTED,
                    halign='left', valign='top', size_hint=(0.78, None),
                    text_size=(dp(280), None), padding=(dp(16), 0))
        tip.bind(size=lambda w, _: setattr(w, 'height', w.text_size[1] + dp(8)))
        self.msg_box.add_widget(tip)
        self.scroll_to_bottom()

    def _rollover_bg(self):
        try:
            self.hm.rollover()
        except Exception as e:
            print('翻页失败:', e)

    # ---------- 互动小说 ----------
    def toggle_tavern(self):
        if not self.hm:
            return
        self.hm.cfg['tavern_mode'] = not self.hm.cfg.get('tavern_mode', False)
        ai_core.save_config(self.hm.cfg)
        if not self.hm.cfg['tavern_mode']:
            self._hide_choices()
        self.refresh_tavern_btn()
        self._refresh_header()

    def refresh_tavern_btn(self):
        on = bool(self.hm and self.hm.cfg.get('tavern_mode'))
        self.tavern_btn.text = '小说开' if on else '小说关'
        self.tavern_btn.fill_color = PRIMARY if on else PRIMARY_SOFT
        self.tavern_btn.pressed_color = PRIMARY_DARK if on else (0.84, 0.82, 0.94, 1)
        self.tavern_btn.color = TEXT_WHITE if on else PRIMARY_DARK

    def render_choices(self, ai_text):
        self.choices_box.clear_widgets()
        self.choices_box.height = 0
        self._hide_choices()
        _, choices = ai_core.parse_choices(ai_text or '')
        if not choices:
            return
        self.choices_box.add_widget(_label('接下来想怎么走？', color=MUTED,
                                           font_size=sp(12), size_hint_y=None,
                                           height=dp(24)))
        for c in choices:
            b = ModernButton(text='  ' + c,
                       size_hint_y=None, height=dp(42),
                       background_color=PRIMARY_SOFT, color=PRIMARY_DARK,
                       halign='left', padding=(dp(12), 0), font_size=sp(13))
            b.bind(on_release=lambda w, choice=c: self.choose(choice))
            self.choices_box.add_widget(b)
        target_height = dp(24) + dp(42) * len(choices) + dp(6) * len(choices) + dp(16)
        Animation.cancel_all(self.choices_panel, 'height', 'opacity')
        self.choices_panel.height = 0
        self.choices_panel.opacity = 0
        Animation(height=target_height, opacity=1, d=0.18,
                  t='out_quad').start(self.choices_panel)

    def _hide_choices(self):
        """Collapse the option tray instead of leaving an empty white surface."""
        if not hasattr(self, 'choices_panel'):
            return
        Animation.cancel_all(self.choices_panel, 'height', 'opacity')
        self.choices_panel.opacity = 0
        self.choices_panel.height = 0

    def choose(self, choice):
        self.choices_box.clear_widgets()
        self.choices_box.height = 0
        self._hide_choices()
        self.input.text = choice
        self.send()

    # ---------- 气泡操作（长按菜单 / 重新生成 / 编辑 / 删除） ----------
    def _find_msg_index(self, content, is_user):
        """按内容从后往前定位消息索引（用于编辑/删除）。"""
        role = 'user' if is_user else 'assistant'
        for i in range(len(self.hm.messages) - 1, -1, -1):
            m = self.hm.messages[i]
            if m.get('role') == role and (m.get('content') or '') == content:
                return i
        return None

    def regen(self):
        """重新生成：删掉最后一条 AI 回复，重发最后一条用户消息。"""
        if self.busy or not self.hm:
            return
        text = self.hm.truncate_after_last_user()
        if text is None:
            return
        self.rebuild_bubbles()
        self.busy = True
        self.set_input_enabled(False)
        threading.Thread(target=self._run, args=(text, False), daemon=True).start()

    def show_bubble_menu(self, bubble, is_user):
        if self.busy or not self.hm:
            return
        pop = Popup(title='消息操作', title_font=_UI_FONT_NAME,
                    separator_color=PRIMARY, background_color=CARD,
                    size_hint=(0.84, None), height=dp(250))
        box = BoxLayout(orientation='vertical', padding=(dp(14), dp(12)), spacing=dp(8))
        if is_user:
            b_edit = ModernButton(text=_emoji_markup('✏️ 编辑并重新生成'), markup=_EMOJI_MARKUP_AVAILABLE,
                            background_color=FIELD_BG, color=TEXT_DARK, font_size=sp(13))
            b_edit.bind(on_release=lambda *_: (pop.dismiss(), self.edit_bubble(bubble)))
            box.add_widget(b_edit)
        else:
            b_regen = ModernButton(text=_emoji_markup('🔄 重新生成'), markup=_EMOJI_MARKUP_AVAILABLE,
                             background_color=FIELD_BG, color=TEXT_DARK, font_size=sp(13))
            b_regen.bind(on_release=lambda *_: (pop.dismiss(), self.regen()))
            box.add_widget(b_regen)
        b_del = ModernButton(text=_emoji_markup('🗑 删除'), markup=_EMOJI_MARKUP_AVAILABLE,
                       background_color=(1.0, 0.91, 0.93, 1), color=DANGER,
                       font_size=sp(13))
        b_del.bind(on_release=lambda *_: (pop.dismiss(), self.delete_bubble(bubble, is_user)))
        box.add_widget(b_del)
        b_cancel = ModernButton(text='取消', background_color=FIELD_BG, color=TEXT_DARK,
                                font_size=sp(13))
        b_cancel.bind(on_release=lambda *_: pop.dismiss())
        box.add_widget(b_cancel)
        pop.add_widget(box)
        pop.open()

    def edit_bubble(self, bubble):
        """编辑用户消息：改内容 → 其后的对话作废 → 自动重新生成。"""
        idx = self._find_msg_index(bubble.raw_text, True)
        if idx is None:
            return
        pop = Popup(title='编辑消息', title_font=_UI_FONT_NAME,
                    separator_color=PRIMARY, background_color=CARD,
                    size_hint=(0.92, 0.68))
        box = BoxLayout(orientation='vertical', padding=(dp(14), dp(12)), spacing=dp(8))
        t_input = ModernTextInput(text=bubble.raw_text, multiline=True, foreground_color=TEXT_DARK,
                                  background_color=FIELD_BG)
        box.add_widget(t_input)
        btns = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        ok = ModernButton(text='保存并重新生成', background_color=PRIMARY, color=TEXT_WHITE,
                          font_size=sp(13))
        cancel = ModernButton(text='取消', background_color=FIELD_BG, color=TEXT_DARK,
                              font_size=sp(13))

        def on_save(_):
            new_text = t_input.text.strip()
            if not new_text:
                return
            self.hm.messages[idx]['content'] = new_text
            del self.hm.messages[idx + 1:]  # 旧内容衍生的后续对话作废
            ai_core.save_page_file(self.hm.max_page, self.hm.messages)
            pop.dismiss()
            self.rebuild_bubbles()
            self.busy = True
            self.set_input_enabled(False)
            threading.Thread(target=self._run, args=(new_text, False), daemon=True).start()

        ok.bind(on_release=on_save)
        cancel.bind(on_release=lambda *_: pop.dismiss())
        btns.add_widget(ok)
        btns.add_widget(cancel)
        box.add_widget(btns)
        pop.add_widget(box)
        pop.open()

    def delete_bubble(self, bubble, is_user):
        idx = self._find_msg_index(bubble.raw_text, is_user)
        if idx is None:
            return
        self.hm.messages.pop(idx)
        ai_core.save_page_file(self.hm.max_page, self.hm.messages)
        self.rebuild_bubbles()

    # ---------- 新对话 ----------
    def new_chat(self):
        if self.busy or not self.hm:
            return
        self.msg_box.clear_widgets()
        self.choices_box.clear_widgets()
        self.choices_box.height = 0
        self._hide_choices()
        self.hm.new_chat()
        self._update_empty_state()


# --------------------------------------------------------------------------- #
# 世界书管理页
# --------------------------------------------------------------------------- #
class WorldbookScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.build_ui()

    def build_ui(self):
        root = BoxLayout(orientation='vertical', padding=(dp(18), 0, dp(18), 0),
                         spacing=dp(8))
        # Worldbook is a focused list page: title bar, search, then dense rows.
        top = BoxLayout(size_hint_y=None, height=dp(72), padding=(0, dp(12)),
                        spacing=dp(8))
        heading = BoxLayout(orientation='vertical', spacing=dp(1))
        heading.add_widget(_label('世界书', bold=True, font_size=sp(22), size_hint_y=None,
                                  height=dp(31)))
        self.count_lbl = _label('管理会影响角色行为的设定', color=MUTED,
                                font_size=sp(11), size_hint_y=None, height=dp(20))
        heading.add_widget(self.count_lbl)
        top.add_widget(heading)
        top.add_widget(Widget())
        add_btn = ModernButton(text='新增', size_hint_x=None, width=dp(64),
                               height=dp(34), background_color=PRIMARY,
                               color=TEXT_WHITE, font_size=sp(12),
                               button_radius=[dp(17)] * 4)
        add_btn.bind(on_release=lambda *_: self.edit_entry(None))
        top.add_widget(add_btn)
        root.add_widget(top)

        search_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        self.search_input = ModernTextInput(hint_text='搜索标题、关键词或内容…',
                                            multiline=False, background_color=FIELD_BG,
                                            padding=(dp(12), dp(9)))
        self.search_input.bind(text=lambda *_: self.refresh())
        search_row.add_widget(self.search_input)
        root.add_widget(search_row)

        self.list_scroll = ScrollView(bar_width=dp(3), bar_color=PRIMARY,
                                      bar_inactive_color=DIVIDER,
                                      scroll_type=['bars', 'content'])
        self.list_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=0,
                                  padding=(0, dp(8), 0, dp(76)))
        self.list_box.bind(minimum_height=self.list_box.setter('height'))
        self.list_scroll.add_widget(self.list_box)
        root.add_widget(self.list_scroll)
        self.add_widget(root)

    def on_enter(self):
        self.refresh()

    @_guard
    def refresh(self):
        self.list_box.clear_widgets()
        query = (self.search_input.text or '').strip().casefold() if hasattr(self, 'search_input') else ''
        visible = 0
        for wb in ai_core.load_worldbooks():
            for i, e in enumerate(wb.get('entries', [])):
                title = e.get('title') or '未命名'
                kw = '，'.join(e.get('primary_keywords') or []) or '（无关键词·常驻）'
                searchable = ' '.join((title, kw, e.get('content') or '')).casefold()
                if query and query not in searchable:
                    continue
                visible += 1
                status = e.get('status', 'green')
                status_text = {'blue': '常驻', 'green': '关键词触发', 'red': '已禁用'}.get(status, status)
                status_color = {'blue': PRIMARY, 'green': SUCCESS, 'red': DANGER}.get(status, MUTED)
                row = BoxLayout(size_hint_y=None, height=dp(78), spacing=dp(8),
                                padding=(0, dp(8)))
                info = BoxLayout(orientation='vertical', spacing=dp(2), size_hint_x=1)
                info.add_widget(_label(title, bold=True, font_size=sp(14),
                                       size_hint_y=None, height=dp(26)))
                info.add_widget(_label(kw, color=MUTED, font_size=sp(11),
                                       size_hint_y=None, height=dp(22)))
                preview = (e.get('content') or '').replace('\n', ' ').strip()
                info.add_widget(_label(preview[:44] + ('…' if len(preview) > 44 else ''),
                                       color=MUTED, font_size=sp(10), size_hint_y=None,
                                       height=dp(20)))
                row.add_widget(info)
                status_lbl = _label(status_text, color=status_color, bold=True,
                                    font_size=sp(11), size_hint_x=None, width=dp(62),
                                    halign='center')
                row.add_widget(status_lbl)
                ebtn = ModernButton(text='编辑', size_hint_x=None, width=dp(48),
                              background_color=FIELD_BG, color=TEXT_DARK,
                              font_size=sp(11), button_radius=[dp(15)] * 4)
                ebtn.bind(on_release=lambda w, bk=wb, en=e: self.edit_entry(en, bk))
                row.add_widget(ebtn)
                dbtn = ModernButton(text='删除', size_hint_x=None, width=dp(48),
                              background_color=(1.0, 0.91, 0.93, 1), color=DANGER,
                              font_size=sp(11), button_radius=[dp(15)] * 4)
                dbtn.bind(on_release=lambda w, bk=wb, en=e: self.delete_entry(bk, en))
                row.add_widget(dbtn)
                row_wrap = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(79))
                row_wrap.add_widget(row)
                row_wrap.add_widget(Divider())
                self.list_box.add_widget(row_wrap)
        self.count_lbl.text = '%d 个条目%s' % (visible, ' · 已过滤' if query else '')
        if not visible:
            empty = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(150),
                              padding=(dp(18), dp(16)), spacing=dp(4))
            empty.add_widget(_label('还没有匹配的设定', bold=True, font_size=sp(16),
                                    halign='center', size_hint_y=None, height=dp(30)))
            empty.add_widget(_label('新增一条世界书内容，让角色拥有更稳定的背景记忆。',
                                    color=MUTED, font_size=sp(11), halign='center',
                                    size_hint_y=None, height=dp(42)))
            self.list_box.add_widget(empty)

    @_guard
    def edit_entry(self, entry,  wb=None):
        """新增或编辑条目（Popup 表单）。"""
        if wb is None:
            books = ai_core.load_worldbooks()
            if not books:
                wb = ai_core.save_worldbook(ai_core.default_worldbook())
            else:
                wb = books[0]
        e = dict(entry or ai_core.default_entry())

        form = BoxLayout(orientation='vertical', padding=(dp(14), dp(12)), spacing=dp(7),
                         size_hint_y=None)
        form.bind(minimum_height=form.setter('height'))

        def field(label, value, hint='', multiline=False, height=44):
            form.add_widget(_label(label, color=MUTED, font_size=sp(11),
                                   size_hint_y=None, height=dp(20)))
            ti = ModernTextInput(text=value, hint_text=hint, multiline=multiline,
                                 size_hint_y=None, height=dp(height),
                                 background_color=FIELD_BG, padding=(dp(12), dp(9)))
            form.add_widget(ti)
            return ti

        t_title = field('标题', e.get('title') or '未命名条目', '例如：角色的童年经历')
        t_content = field('设定内容', e.get('content') or '', '触发后会注入给模型的内容',
                          multiline=True, height=105)
        t_kw = field('关键词', '，'.join(e.get('primary_keywords') or []),
                     '多个关键词用逗号分隔；留空表示常驻')
        t_memo = field('备注（仅自己可见）', e.get('memo') or '', '可选',
                       multiline=True, height=65)

        status_labels = {'blue': '常驻', 'green': '关键词触发', 'red': '已禁用'}
        status_values = tuple(status_labels.values())
        position_labels = {
            'before_char': '角色设定前', 'after_char': '角色设定后',
            'before_an': '回复前', 'after_an': '回复后', 'depth': '对话深度',
        }
        position_values = tuple(position_labels.values())
        form.add_widget(_label('注入状态与位置', color=MUTED, font_size=sp(11),
                               size_hint_y=None, height=dp(20)))
        selectors = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        st_spin = Spinner(text=status_labels.get(e.get('status', 'green'), '关键词触发'),
                          values=status_values, background_color=FIELD_BG,
                          color=TEXT_DARK, font_name=_UI_FONT_NAME)
        pos_spin = Spinner(text=position_labels.get(e.get('position', 'before_char'), '角色设定前'),
                           values=position_values, background_color=FIELD_BG,
                           color=TEXT_DARK, font_name=_UI_FONT_NAME)
        selectors.add_widget(st_spin)
        selectors.add_widget(pos_spin)
        form.add_widget(selectors)
        t_order = field('顺序值', str(e.get('order', 100)), '数字越大越靠后', height=44)

        content = Popup(title='编辑世界书条目' if entry else '新增世界书条目',
                        title_font=_UI_FONT_NAME, separator_color=PRIMARY,
                        background_color=CARD, size_hint=(0.94, 0.92))
        outer = BoxLayout(orientation='vertical', padding=dp(4))
        form_scroll = ScrollView(do_scroll_x=False, bar_width=dp(3),
                                 bar_color=PRIMARY, bar_inactive_color=DIVIDER)
        form_scroll.add_widget(form)
        outer.add_widget(form_scroll)
        btns = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        ok = ModernButton(text='保存条目', background_color=PRIMARY, color=TEXT_WHITE,
                          font_size=sp(13))
        cancel = ModernButton(text='取消', background_color=FIELD_BG, color=TEXT_DARK,
                              font_size=sp(13))

        def on_save(_):
            try:
                e['title'] = t_title.text.strip() or '未命名条目'
                e['content'] = t_content.text
                e['primary_keywords'] = [k.strip() for k in re.split(r'[,，\n]+', t_kw.text) if k.strip()] \
                    if t_kw.text.strip() else []
                e['memo'] = t_memo.text.strip()
                e['status'] = {v: k for k, v in status_labels.items()}.get(st_spin.text, 'green')
                e['position'] = {v: k for k, v in position_labels.items()}.get(pos_spin.text, 'before_char')
                try:
                    e['order'] = int(t_order.text.strip())
                except Exception:
                    e['order'] = 100
                wb['entries'] = [x for x in wb.get('entries', []) if x is not entry]
                wb['entries'].append(e)
                ai_core.save_worldbook(wb)
                content.dismiss()
                self.refresh()
            except Exception as ex:
                import traceback as _tb
                show_error('保存失败', ''.join(_tb.format_exception_only(type(ex), ex))[:240])

        ok.bind(on_release=on_save)
        cancel.bind(on_release=lambda *_: content.dismiss())
        btns.add_widget(ok)
        btns.add_widget(cancel)
        outer.add_widget(btns)
        content.content = outer
        content.open()

    @_guard
    def delete_entry(self, wb, entry):
        title = entry.get('title') or '未命名条目'
        pop = Popup(title='删除世界书条目', title_font=_UI_FONT_NAME,
                    separator_color=DANGER, background_color=CARD,
                    size_hint=(0.86, None), height=dp(190))
        box = BoxLayout(orientation='vertical', padding=(dp(14), dp(12)), spacing=dp(8))
        box.add_widget(_label('确定删除「%s」吗？' % title, font_size=sp(14),
                              halign='center', size_hint_y=None, height=dp(34)))
        box.add_widget(_label('删除后不会影响已经生成的聊天记录。', color=MUTED,
                              font_size=sp(11), halign='center', size_hint_y=None,
                              height=dp(28)))
        actions = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        cancel = ModernButton(text='取消', background_color=FIELD_BG,
                              color=TEXT_DARK, font_size=sp(13))
        confirm = ModernButton(text='确认删除', background_color=(1.0, 0.91, 0.93, 1),
                               color=DANGER, font_size=sp(13))
        cancel.bind(on_release=lambda *_: pop.dismiss())

        def do_delete(_):
            try:
                wb['entries'] = [x for x in wb.get('entries', []) if x is not entry]
                ai_core.save_worldbook(wb)
                pop.dismiss()
                self.refresh()
            except Exception as ex:
                import traceback as _tb
                show_error('删除失败', ''.join(_tb.format_exception_only(type(ex), ex))[:240])

        confirm.bind(on_release=do_delete)
        actions.add_widget(cancel)
        actions.add_widget(confirm)
        box.add_widget(actions)
        pop.content = box
        pop.open()


# --------------------------------------------------------------------------- #
# 设置页
# --------------------------------------------------------------------------- #
class SettingsScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.fields = {}
        self.build_ui()

    def build_ui(self):
        root = BoxLayout(orientation='vertical', padding=(dp(18), 0, dp(18), 0),
                         spacing=dp(8))
        top = BoxLayout(size_hint_y=None, height=dp(72), padding=(0, dp(12)))
        heading = BoxLayout(orientation='vertical', spacing=dp(1))
        heading.add_widget(_label('设置', bold=True, font_size=sp(22), size_hint_y=None,
                                  height=dp(31)))
        heading.add_widget(_label('连接、角色和回复行为都保存在本机', color=MUTED,
                                 font_size=sp(11), size_hint_y=None, height=dp(20)))
        top.add_widget(heading)
        root.add_widget(top)

        scroll = ScrollView(bar_width=dp(3), bar_color=PRIMARY,
                            bar_inactive_color=DIVIDER,
                            scroll_type=['bars', 'content'])
        form = BoxLayout(orientation='vertical', spacing=dp(7), padding=(0, dp(4), 0, dp(74)),
                         size_hint_y=None)
        form.bind(minimum_height=form.setter('height'))

        def group(title, subtitle):
            form.add_widget(_section_header(title, subtitle))
            form.add_widget(Widget(size_hint_y=None, height=dp(3)))

        def field(label, key, hint='', multiline=False, password=False):
            input_height = dp(94) if multiline else dp(44)
            form.add_widget(_label(label, color=MUTED, font_size=sp(11),
                                   size_hint_y=None, height=dp(20)))
            ti = ModernTextInput(hint_text=hint, multiline=multiline,
                                 password=password, size_hint_y=None,
                                 height=input_height, background_color=FIELD_BG,
                                 foreground_color=TEXT_DARK)
            form.add_widget(ti)
            form.add_widget(Widget(size_hint_y=None, height=dp(6)))
            self.fields[key] = ti

        group('连接与模型', '兼容 OpenAI 风格接口；API Key 只保存在当前设备')
        field('API 地址', 'base_url', '例如：https://api.example.com')
        field('API Key', 'api_key', '输入你的密钥', password=True)
        field('模型名', 'model', '例如：deepseek-chat 或 gpt-5.6-luna')

        group('角色与世界', '这些内容会影响每一轮对话的上下文')
        field('人设提示词', 'persona_prompt', '角色的性格、语气和行为规则', multiline=True)
        field('世界观', 'worldview_prompt', '背景设定；也可以在世界书中细化', multiline=True)
        field('玩家身份', 'player_identity', '你在故事中的身份', multiline=True)

        group('回复风格', '可选；留空时使用默认行为')
        field('示例对话', 'dialogue_examples', '用几轮对话示范角色的说话方式', multiline=True)
        field('开场白', 'opening_message', '新话题的第一条 AI 消息', multiline=True)
        field('前置提示词', 'raw_prefix', '高级选项：原样放在上下文最前面', multiline=True)

        group('生成与记忆', '按需开启功能，设置会立即保存')
        field('温度（0～2）', 'temperature', '默认 0.8')

        def toggle(label, description, checkbox):
            card = BoxLayout(size_hint_y=None, height=dp(60), padding=(0, dp(7)),
                             spacing=dp(8))
            copy = BoxLayout(orientation='vertical', spacing=dp(1))
            copy.add_widget(_label(label, font_size=sp(13), size_hint_y=None, height=dp(23)))
            copy.add_widget(_label(description, color=MUTED, font_size=sp(10),
                                   size_hint_y=None, height=dp(20)))
            card.add_widget(copy)
            checkbox.size_hint_x = None
            checkbox.width = dp(42)
            card.add_widget(checkbox)
            form.add_widget(card)
            form.add_widget(Divider())

        self.ck_thinking = CheckBox(active=False)
        self.ck_bm25 = CheckBox(active=True)
        self.ck_search = CheckBox(active=True)
        self.ck_delai = CheckBox(active=False)
        toggle('先想再答', '显示模型返回的思考过程（如果接口支持）', self.ck_thinking)
        toggle('BM25 旧对话记忆', '在较长对话中检索以前的相关内容', self.ck_bm25)
        toggle('翻旧账工具', '允许模型主动检索历史对话', self.ck_search)
        toggle('减少 AI 腔', '普通聊天中尽量使用更自然的表达', self.ck_delai)
        scroll.add_widget(form)
        root.add_widget(scroll)

        save_bar = BoxLayout(size_hint_y=None, height=dp(62), padding=(0, dp(8)),
                             spacing=dp(8))
        self.save_status = _label('修改只保存在当前设备', color=MUTED, font_size=sp(11))
        save_bar.add_widget(self.save_status)
        save_btn = ModernButton(text='保存设置',
                                size_hint_x=None, width=dp(112),
                                background_color=PRIMARY, color=TEXT_WHITE,
                                font_size=sp(13), button_radius=[dp(17)] * 4)
        save_btn.bind(on_release=lambda *_: self.save_cfg())
        save_bar.add_widget(save_btn)
        root.add_widget(save_bar)
        self.add_widget(root)

    def on_enter(self):
        cfg = ai_core.load_config()
        for k, ti in self.fields.items():
            v = cfg.get(k)
            if isinstance(v, (int, float)):
                ti.text = str(v)
            else:
                ti.text = str(v or '')
        self.ck_thinking.active = bool(cfg.get('enable_thinking'))
        self.ck_bm25.active = bool(cfg.get('enable_bm25', True))
        self.ck_search.active = bool(cfg.get('enable_search_tool', True))
        self.ck_delai.active = bool(cfg.get('enable_delai'))

    def save_cfg(self):
        cfg = ai_core.load_config()
        for k, ti in self.fields.items():
            if k == 'temperature':
                try:
                    cfg[k] = float(ti.text.strip())
                except Exception:
                    pass
            else:
                cfg[k] = ti.text.strip() if k != 'api_key' else ti.text.strip()
        cfg['enable_thinking'] = self.ck_thinking.active
        cfg['enable_bm25'] = self.ck_bm25.active
        cfg['enable_search_tool'] = self.ck_search.active
        cfg['enable_delai'] = self.ck_delai.active
        ai_core.save_config(cfg)
        app = App.get_running_app()
        if app and hasattr(app, 'chat') and app.chat.hm:
            app.chat.hm.cfg = cfg
            app.chat.refresh_tavern_btn()
            app.chat._refresh_header()
        self.save_status.text = '✓ 已保存，下一条消息立即生效'
        self.save_status.color = SUCCESS
        Clock.schedule_once(lambda *_: self._reset_save_status(), 2.5)

    def _reset_save_status(self):
        if hasattr(self, 'save_status'):
            self.save_status.text = '修改只保存在当前设备'
            self.save_status.color = MUTED


# --------------------------------------------------------------------------- #
# 底部导航 + App
# --------------------------------------------------------------------------- #
class NavBar(BoxLayout):
    """Slim bottom navigation with a single active pill."""

    def __init__(self, on_select=None, **kwargs):
        super().__init__(orientation='horizontal', **kwargs)
        self.on_select = on_select
        self.buttons = {}

    def add_tab(self, text, name):
        button = ModernButton(text=text, background_color=(0, 0, 0, 0),
                              color=MUTED, font_size=sp(12),
                              button_radius=[dp(17)] * 4)
        button.bind(on_release=lambda *_: self._select(name))
        self.buttons[name] = button
        self.add_widget(button)

    def _select(self, name):
        if self.on_select:
            self.on_select(name)

    def set_active(self, name):
        for tab_name, button in self.buttons.items():
            active = tab_name == name
            button.fill_color = PRIMARY_SOFT if active else (0, 0, 0, 0)
            button.pressed_color = (0.84, 0.82, 0.94, 1) if active else (0.94, 0.93, 0.97, 1)
            button.color = PRIMARY_DARK if active else MUTED


class PetApp(App):
    def build(self):
        self.title = '酒馆'
        sm = ScreenManager()
        self.screen_manager = sm
        self.chat = ChatScreen(name='chat')
        self.world = WorldbookScreen(name='world')
        self.settings = SettingsScreen(name='settings')
        sm.add_widget(self.chat)
        sm.add_widget(self.world)
        sm.add_widget(self.settings)

        root = BoxLayout(orientation='vertical')
        root.add_widget(sm)
        nav_surface = SurfaceBox(size_hint_y=None, height=dp(62), padding=(dp(14), dp(6)),
                                 spacing=dp(6), surface_color=CARD,
                                 border_color=(0, 0, 0, 0),
                                 surface_radius=[dp(20)] * 4)

        def go(name):
            sm.current = name

        nav = NavBar(on_select=go, spacing=dp(6))
        for text, name in (('聊天', 'chat'), ('世界书', 'world'), ('设置', 'settings')):
            nav.add_tab(text, name)
        nav_surface.add_widget(nav)
        root.add_widget(nav_surface)
        sm.bind(current=lambda _, name: nav.set_active(name))
        nav.set_active('chat')
        return root


if __name__ == '__main__':
    install_crash_handler()
    PetApp().  run()
