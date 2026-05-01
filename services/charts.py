"""
services/charts.py — генерация графиков через matplotlib.

Все функции возвращают bytes (PNG) — готово для отправки через bot.send_photo().

Графики:
  1. pie_chart()        — круговая диаграмма расходов по категориям
  2. bar_monthly()      — столбчатый график доходов/расходов за месяц
  3. line_yearly()      — линейный график за год (12 месяцев)
  4. hbar_categories()  — горизонтальные бары топ-категорий
"""

import io
import logging
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # без GUI — обязательно для сервера
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="matplotlib")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.ticker import FuncFormatter

logger = logging.getLogger(__name__)

# ── Цветовая палитра (тёмная тема) ──────────────────────────────────────────
BG_COLOR     = "#1a1a2e"
BG_AXES      = "#16213e"
TEXT_COLOR   = "#e0e0e0"
GRID_COLOR   = "#2a2a4a"
ACCENT_GREEN = "#00d084"
ACCENT_RED   = "#ff4757"
ACCENT_BLUE  = "#3498db"

CATEGORY_COLORS = [
    "#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6",
    "#1abc9c", "#e67e22", "#e91e63", "#00bcd4", "#8bc34a",
    "#ff5722", "#607d8b", "#795548", "#9c27b0", "#cddc39",
]


def _apply_dark_style(fig, ax_list):
    """Применяет тёмную тему ко всем осям."""
    fig.patch.set_facecolor(BG_COLOR)
    for ax in ax_list:
        ax.set_facecolor(BG_AXES)
        ax.tick_params(colors=TEXT_COLOR, labelsize=9)
        ax.xaxis.label.set_color(TEXT_COLOR)
        ax.yaxis.label.set_color(TEXT_COLOR)
        ax.title.set_color(TEXT_COLOR)
        for spine in ax.spines.values():
            spine.set_edgecolor(GRID_COLOR)


def _fig_to_bytes(fig) -> bytes:
    """Конвертирует matplotlib figure в PNG bytes."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return buf.read()


def _fmt_money(x, _):
    """Форматтер оси Y: 15000 → 15K."""
    if x >= 1_000_000:
        return f"{x/1_000_000:.1f}M"
    if x >= 1_000:
        return f"{x/1_000:.0f}K"
    return f"{x:.0f}"


# ════════════════════════════════════════════════════════════════════════════
# 1. КРУГОВАЯ ДИАГРАММА — расходы по категориям
# ════════════════════════════════════════════════════════════════════════════

def pie_chart(
    categories: list[dict],
    title: str = "Расходы по категориям",
    currency: str = "с",
) -> bytes:
    """
    categories: [{"name": "Еда", "icon": "🍔", "total": 5000}, ...]
    """
    if not categories:
        return _empty_chart("Нет данных для отображения")

    # Топ-8, остальное в «Прочее»
    sorted_cats = sorted(categories, key=lambda x: x["total"], reverse=True)
    if len(sorted_cats) > 8:
        top     = sorted_cats[:7]
        other   = sum(c["total"] for c in sorted_cats[7:])
        top.append({"name": "Прочее", "icon": "❓", "total": other})
    else:
        top = sorted_cats

    labels = [c['name'] for c in top]
    sizes  = [c["total"] for c in top]
    total  = sum(sizes)
    colors = CATEGORY_COLORS[:len(top)]

    fig, ax = plt.subplots(figsize=(7, 5))
    _apply_dark_style(fig, [ax])

    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=None,
        colors=colors,
        autopct=lambda p: f"{p:.1f}%" if p > 4 else "",
        startangle=140,
        wedgeprops={"linewidth": 1.5, "edgecolor": BG_COLOR},
        pctdistance=0.75,
    )
    for at in autotexts:
        at.set_color(TEXT_COLOR)
        at.set_fontsize(8)
        at.set_fontweight("bold")

    # Легенда
    legend_labels = [f"{l}  —  {s:,.0f} {currency}".replace(",", " ")
                     for l, s in zip(labels, sizes)]
    patches = [mpatches.Patch(color=c, label=lb)
               for c, lb in zip(colors, legend_labels)]
    ax.legend(handles=patches, loc="center left", bbox_to_anchor=(1, 0.5),
              fontsize=8, framealpha=0, labelcolor=TEXT_COLOR)

    ax.set_title(f"{title}\nВсего: {total:,.0f} {currency}".replace(",", " "),
                 color=TEXT_COLOR, fontsize=11, pad=12)
    fig.tight_layout()
    return _fig_to_bytes(fig)


# ════════════════════════════════════════════════════════════════════════════
# 2. СТОЛБЧАТЫЙ ГРАФИК — доходы и расходы по дням месяца
# ════════════════════════════════════════════════════════════════════════════

def bar_monthly(
    summary: dict,
    year: int,
    month: int,
    currency: str = "с",
) -> bytes:
    """
    summary: результат get_monthly_summary()
    Рисует: столбцы расходов по категориям + линия дохода.
    """
    cats = summary.get("expenses_by_category", [])
    if not cats:
        return _empty_chart("Нет расходов за этот месяц")

    from utils.formatters import MONTH_NAMES
    month_name = MONTH_NAMES[month - 1]

    # Данные
    names   = [c['name'] for c in cats[:10]]
    amounts = [c["total"] for c in cats[:10]]
    colors  = CATEGORY_COLORS[:len(names)]
    total_exp = summary["total_expenses"]
    total_inc = summary["total_income"]

    fig, ax = plt.subplots(figsize=(8, 5))
    _apply_dark_style(fig, [ax])

    bars = ax.bar(names, amounts, color=colors, edgecolor=BG_COLOR,
                  linewidth=0.8, zorder=3)

    # Подписи над столбцами
    for bar, amt in zip(bars, amounts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + total_exp * 0.01,
            f"{amt:,.0f}".replace(",", " "),
            ha="center", va="bottom", fontsize=7.5,
            color=TEXT_COLOR, fontweight="bold",
        )

    # Линия общего дохода
    if total_inc > 0:
        ax.axhline(total_inc, color=ACCENT_GREEN, linewidth=1.5,
                   linestyle="--", zorder=4, label=f"Доход: {total_inc:,.0f} {currency}".replace(",", " "))
        ax.legend(fontsize=8, framealpha=0, labelcolor=ACCENT_GREEN)

    ax.set_title(f"Расходы по категориям — {month_name} {year}",
                 color=TEXT_COLOR, fontsize=11, pad=10)
    ax.set_ylabel(f"Сумма ({currency})", color=TEXT_COLOR, fontsize=9)
    ax.yaxis.set_major_formatter(FuncFormatter(_fmt_money))
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.5, zorder=0)
    ax.tick_params(axis="x", rotation=30, labelsize=8)
    fig.tight_layout()
    return _fig_to_bytes(fig)


# ════════════════════════════════════════════════════════════════════════════
# 3. ЛИНЕЙНЫЙ ГРАФИК — доходы и расходы по месяцам года
# ════════════════════════════════════════════════════════════════════════════

def line_yearly(
    yearly_data: list[dict],
    year: int,
    currency: str = "с",
) -> bytes:
    """
    yearly_data: результат get_yearly_summary()
    """
    if not yearly_data:
        return _empty_chart(f"Нет данных за {year} год")

    from utils.formatters import MONTH_NAMES
    short_months = [m[:3] for m in MONTH_NAMES]

    # Заполняем все 12 месяцев (пустые → 0)
    expenses = [0.0] * 12
    incomes  = [0.0] * 12
    for row in yearly_data:
        idx = int(row["month"]) - 1
        expenses[idx] = row["expenses"]
        incomes[idx]  = row["income"]

    fig, ax = plt.subplots(figsize=(9, 5))
    _apply_dark_style(fig, [ax])

    x = list(range(12))
    ax.fill_between(x, expenses, alpha=0.15, color=ACCENT_RED)
    ax.fill_between(x, incomes,  alpha=0.15, color=ACCENT_GREEN)
    ax.plot(x, expenses, color=ACCENT_RED,   linewidth=2,
            marker="o", markersize=5, label="Расходы")
    ax.plot(x, incomes,  color=ACCENT_GREEN, linewidth=2,
            marker="o", markersize=5, label="Доходы")

    # Подписи точек
    for i, (e, inc) in enumerate(zip(expenses, incomes)):
        if e > 0:
            ax.annotate(f"{e/1000:.0f}K", (i, e), textcoords="offset points",
                        xytext=(0, 8), ha="center", fontsize=7, color=ACCENT_RED)
        if inc > 0:
            ax.annotate(f"{inc/1000:.0f}K", (i, inc), textcoords="offset points",
                        xytext=(0, 8), ha="center", fontsize=7, color=ACCENT_GREEN)

    total_balance = sum(incomes) - sum(expenses)
    balance_color = ACCENT_GREEN if total_balance >= 0 else ACCENT_RED
    balance_sign  = "+" if total_balance >= 0 else ""

    ax.set_title(
        f"Доходы и расходы за {year} год\n"
        f"Баланс: {balance_sign}{total_balance:,.0f} {currency}".replace(",", " "),
        color=TEXT_COLOR, fontsize=11, pad=10,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(short_months, color=TEXT_COLOR, fontsize=9)
    ax.yaxis.set_major_formatter(FuncFormatter(_fmt_money))
    ax.grid(color=GRID_COLOR, linewidth=0.5, alpha=0.7)
    ax.legend(fontsize=9, framealpha=0, labelcolor=TEXT_COLOR)
    fig.tight_layout()
    return _fig_to_bytes(fig)


# ════════════════════════════════════════════════════════════════════════════
# 4. ГОРИЗОНТАЛЬНЫЕ БАРЫ — топ категорий с % от общего
# ════════════════════════════════════════════════════════════════════════════

def hbar_categories(
    categories: list[dict],
    title: str = "Топ категорий",
    currency: str = "с",
) -> bytes:
    if not categories:
        return _empty_chart("Нет данных")

    top    = sorted(categories, key=lambda x: x["total"], reverse=True)[:10]
    total  = sum(c["total"] for c in top)
    labels = [c['name'] for c in top]
    values = [c["total"] for c in top]
    colors = CATEGORY_COLORS[:len(top)]

    fig, ax = plt.subplots(figsize=(7, max(3, len(top) * 0.55 + 1)))
    _apply_dark_style(fig, [ax])

    bars = ax.barh(labels[::-1], values[::-1], color=colors[::-1],
                   edgecolor=BG_COLOR, linewidth=0.8, height=0.6)

    # Подписи справа от баров
    for bar, val in zip(bars, values[::-1]):
        pct = val / total * 100 if total else 0
        ax.text(
            bar.get_width() + total * 0.005,
            bar.get_y() + bar.get_height() / 2,
            f"{val:,.0f} {currency}  ({pct:.0f}%)".replace(",", " "),
            va="center", fontsize=8, color=TEXT_COLOR,
        )

    ax.set_title(title, color=TEXT_COLOR, fontsize=11, pad=10)
    ax.set_xlabel(f"Сумма ({currency})", color=TEXT_COLOR, fontsize=9)
    ax.xaxis.set_major_formatter(FuncFormatter(_fmt_money))
    ax.grid(axis="x", color=GRID_COLOR, linewidth=0.5)
    ax.set_xlim(0, max(values) * 1.35)
    fig.tight_layout()
    return _fig_to_bytes(fig)


# ════════════════════════════════════════════════════════════════════════════
# УТИЛИТА: пустой график с сообщением
# ════════════════════════════════════════════════════════════════════════════

def _empty_chart(message: str = "Нет данных") -> bytes:
    fig, ax = plt.subplots(figsize=(6, 3))
    _apply_dark_style(fig, [ax])
    ax.text(0.5, 0.5, message, transform=ax.transAxes,
            ha="center", va="center", fontsize=13,
            color=TEXT_COLOR, alpha=0.6)
    ax.axis("off")
    return _fig_to_bytes(fig)