# ============================================================================
# desenho_dcl_coef.py  |  BridgeCalc – Módulo de Desenho Técnico
# ============================================================================
# Descrição : Gera a figura combinada com dois painéis alinhados:
#               [Superior] Gráfico de degraus do coeficiente (φ, CIA, CIV, CNF)
#               [Inferior] Diagrama de Corpo Livre (DCL) da estrutura
#
#             Ambos os painéis compartilham o mesmo eixo X visual, com
#             inserção de gaps visuais para estruturas biapoiadas.
#
# Tamanho   : figsize=(9.51, 5.71), dpi=100 – FIXO para QFrame da UI.
#
# Dependências internas:
#   modules.Gerenciador_Dados         → Superestrutura, CoeficientesImpacto
#   modules.logica_janela_def_superestrutura → MAPA_TIPOS
#
# Versão    : 2.0
# ============================================================================

import matplotlib
matplotlib.use('Agg')

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.gridspec import GridSpec
from typing import Dict, List, Tuple, Union, Callable, Optional

from modules.Gerenciador_Dados import Superestrutura, CoeficientesImpacto

# ─── PALETA DE CORES ────────────────────────────────────────────────────────
COR_FUNDO    = "#2b2b2b"
COR_VIGA     = "#e0e0e0"
COR_VIGA_FG  = "#4a4a4a"
COR_LAJE_FG  = "#3a6186"
COR_LAJE_ED  = "#90CAF9"
COR_APOIO    = "#e0e0e0"
COR_ROTULA   = "#e0e0e0"
COR_DIM      = "#909090"
COR_TXT_DIM  = "#bbbbbb"
COR_TXT      = "#ffffff"
COR_COEF     = "#FFA726"   # linha principal do coeficiente
COR_SPINE    = "#555555"   # bordas dos eixos
COR_GRID     = "#3a3a3a"   # grade interna

# Mapeamento de rótulos por tipo de coeficiente
_ROTULOS_COEF: dict = {
    "impacto": "Coef. de Impacto  φ",
    "cia":     "Coef. de Impacto Adicional  (CIA)",
    "civ":     "Coef. de Impacto Vertical   (CIV)",
    "cnf":     "Coef. do Número de Faixas   (CNF)",
}


# ============================================================================
# FUNÇÕES AUXILIARES INTERNAS
# ============================================================================

def _normalizar_tipo(tipo_texto: str) -> str:
    """Converte o texto da UI para o identificador interno de tipologia."""
    _TIPOS_INTERNOS = (
        "biapoiada", "isostatica_em_balanco",
        "hiperestatica_sem_balanco", "hiperestatica_com_balanco"
    )
    if tipo_texto in _TIPOS_INTERNOS:
        return tipo_texto

    from modules.logica_janela_def_superestrutura import MAPA_TIPOS
    return MAPA_TIPOS.get(tipo_texto, "biapoiada")


def _calcular_extensao(tipo_interno: str, vaos: list,
                        laje: Union[float, bool]) -> Tuple[float, float]:
    """
    Calcula a extensão total da estrutura e o fator de escala visual.

    Retorna
    -------
    total_real : float
        Comprimento total em metros.
    fator : float
        Fator de escala (normalizado pela referência de 20 m).
    """
    if tipo_interno == "isostatica_em_balanco":
        soma_vaos = vaos[0] + 2.0 * vaos[1]
    elif tipo_interno == "hiperestatica_sem_balanco":
        soma_vaos = vaos[0] + 2.0 * vaos[1]
    elif tipo_interno == "hiperestatica_com_balanco":
        soma_vaos = vaos[0] + 2.0 * vaos[1] + 2.0 * vaos[2]
    else:
        soma_vaos = sum(vaos)

    total_lajes = (2.0 * laje) if laje else 0.0
    total_real  = soma_vaos + total_lajes
    fator       = max(0.5, total_real / 20.0)
    return total_real, fator


def _criar_mapa_visual(
    superestrutura: Superestrutura
) -> Tuple[
    Callable[[float], float],
    Tuple[float, float],
    List[Tuple[float, float]],
    List[Tuple[float, float]]
]:
    """
    Cria uma função que mapeia coordenadas reais → coordenadas visuais,
    inserindo gaps visuais entre vãos para estruturas biapoiadas.

    Retorna
    -------
    mapa : Callable
        Função de mapeamento real → visual.
    limites : Tuple[float, float]
        (x_min_visual, x_max_visual) com padding.
    segmentos_vaos : List[Tuple[float, float]]
        Lista de (x_vis_ini, x_vis_fim) para cada vão.
    segmentos_lajes : List[Tuple[float, float]]
        Lista de (x_vis_ini, x_vis_fim) para cada laje.
    """
    tipo_interno = _normalizar_tipo(superestrutura.tipo)
    vaos         = superestrutura.vaos
    laje         = superestrutura.laje_transicao
    total_real, fator = _calcular_extensao(tipo_interno, vaos, laje)
    gap_visual = (0.60 + 0.15) * fator  # identico ao desenho_dcl

    # ── Estruturas contínuas: mapeamento identidade ────────────────────────
    if tipo_interno != "biapoiada":
        def mapa(x: float) -> float:  # noqa: E306
            return x

        pad = 1.5 * fator
        segmentos_vaos  = []
        x_real = float(laje) if laje else 0.0
        for v in vaos:
            segmentos_vaos.append((x_real, x_real + v))
            x_real += v

        segmentos_lajes = []
        if laje:
            segmentos_lajes.append((0.0, float(laje)))
            segmentos_lajes.append((total_real - float(laje), total_real))

        return mapa, (-pad, total_real + pad), segmentos_vaos, segmentos_lajes

    # ── Biapoiada: constrói pontos de quebra (real, visual) ───────────────
    boundaries: List[Tuple[float, float]] = []
    x_real   = 0.0
    x_visual = 0.0
    segmentos_lajes: List[Tuple[float, float]] = []
    segmentos_vaos:  List[Tuple[float, float]] = []

    if laje:
        boundaries.append((x_real, x_visual))
        x_real   += float(laje)
        x_visual += float(laje)
        boundaries.append((x_real, x_visual))
        segmentos_lajes.append((boundaries[-2][1], boundaries[-1][1]))

    for i, v in enumerate(vaos):
        boundaries.append((x_real, x_visual))
        x_real   += v
        x_visual += v
        boundaries.append((x_real, x_visual))
        segmentos_vaos.append((boundaries[-2][1], boundaries[-1][1]))
        if i < len(vaos) - 1:
            x_visual += gap_visual

    if laje:
        boundaries.append((x_real, x_visual))
        x_real   += float(laje)
        x_visual += float(laje)
        boundaries.append((x_real, x_visual))
        segmentos_lajes.append((boundaries[-2][1], boundaries[-1][1]))

    def mapa(x: float) -> float:  # noqa: E306
        """Mapeamento linear por segmento."""
        for k in range(len(boundaries) - 1):
            r1, v1 = boundaries[k]
            r2, v2 = boundaries[k + 1]
            if r1 <= x <= r2:
                return v1 + (x - r1)
        # Extrapolação (não deve ocorrer em uso normal)
        if x < boundaries[0][0]:
            return boundaries[0][1] + (x - boundaries[0][0])
        return boundaries[-1][1] + (x - boundaries[-1][0])

    pad       = 1.5 * fator
    x_vis_min = boundaries[0][1]  - pad
    x_vis_max = boundaries[-1][1] + pad
    return mapa, (x_vis_min, x_vis_max), segmentos_vaos, segmentos_lajes


# ============================================================================
# DESENHO DO DCL (PAINEL INFERIOR)
# ============================================================================

def _desenhar_dcl_em_axes(
    ax: plt.Axes,
    superestrutura: Superestrutura,
    mapa: Callable[[float], float],
    segmentos_vaos: List[Tuple[float, float]],
    segmentos_lajes: List[Tuple[float, float]]
) -> Tuple[float, float]:
    """
    Desenha o DCL no eixo fornecido usando coordenadas visuais.

    Retorna
    -------
    (x_vis_min, x_vis_max) : Tuple[float, float]
        Limites visuais aplicados ao eixo.
    """
    tipo_interno      = _normalizar_tipo(superestrutura.tipo)
    vaos              = superestrutura.vaos
    laje              = superestrutura.laje_transicao
    total_real, fator = _calcular_extensao(tipo_interno, vaos, laje)

    # ── Constantes geométricas ────────────────────────────────────────────
    VIGA_H    = 0.20 * fator
    VIGA_BOT  = -VIGA_H
    LAP       = 0.58 * fator
    R_ROT     = 0.10 * fator
    Y_SOLO    = VIGA_BOT - LAP - 0.18 * fator
    N_HACH    = 6
    OFF_COTA  = 1.25 * fator
    Y_DIM     = VIGA_BOT - OFF_COTA
    EXT_H     = 0.09 * fator
    FS_DIM    = max(5.0, 8.0 - fator * 0.30)

    ax.set_facecolor(COR_FUNDO)

    # ── Funções de desenho ────────────────────────────────────────────────

    def draw_viga_seg(x_ini, x_fim, laje_seg=False):
        cor_fg = COR_LAJE_FG if laje_seg else COR_VIGA_FG
        cor_ed = COR_LAJE_ED if laje_seg else COR_VIGA
        ax.add_patch(patches.FancyBboxPatch(
            (x_ini, VIGA_BOT), x_fim - x_ini, VIGA_H,
            boxstyle="square,pad=0",
            facecolor=cor_fg, edgecolor=cor_ed, lw=1.1, zorder=2
        ))

    def draw_apoio(x, fix_xy=False):
        y_base = Y_SOLO + 0.18 * fator
        pts = np.array([[x, VIGA_BOT], [x-LAP/2, y_base], [x+LAP/2, y_base]])
        ax.add_patch(patches.Polygon(
            pts, closed=True, edgecolor=COR_APOIO, facecolor='none',
            lw=1.1, zorder=4
        ))
        ax.plot([x-LAP/2, x+LAP/2], [y_base, y_base], color=COR_APOIO, lw=1.1, zorder=4)
        if fix_xy:
            dy = 0.20 * fator
            dx = 0.14 * fator
            for xi in np.linspace(x-LAP/2, x+LAP/2, N_HACH):
                ax.plot([xi, xi-dx], [y_base, y_base-dy],
                        color=COR_APOIO, lw=0.8, zorder=3)
        else:
            y_rolo = y_base - 0.14 * fator
            ax.plot([x-LAP/2, x+LAP/2], [y_rolo, y_rolo],
                    color=COR_APOIO, lw=1.1, zorder=4)
            for xr in np.linspace(x-LAP/2 + LAP/8, x+LAP/2 - LAP/8, 3):
                ax.add_patch(patches.Circle(
                    (xr, y_base - 0.07*fator), 0.032*fator,
                    facecolor=COR_APOIO, edgecolor='none', zorder=5
                ))

    def draw_rotula(x):
        ax.add_patch(patches.Circle(
            (x, VIGA_BOT), R_ROT,
            edgecolor=COR_ROTULA, facecolor=COR_FUNDO, lw=1.1, zorder=6
        ))
        ax.add_patch(patches.Circle(
            (x, VIGA_BOT), R_ROT*0.3,
            facecolor=COR_ROTULA, edgecolor='none', zorder=7
        ))

    def draw_cota(x_ini, x_fim, valor, y_pos, is_global=False):
        cor = COR_COEF if is_global else COR_DIM
        fs  = FS_DIM + 0.5 if is_global else FS_DIM
        for xp in (x_ini, x_fim):
            ax.plot([xp, xp], [y_pos + EXT_H, y_pos - EXT_H],
                    color=cor, lw=0.5, zorder=3)
        ax.annotate('', xy=(x_ini, y_pos), xytext=(x_fim, y_pos),
                    arrowprops=dict(
                        arrowstyle='<->, head_width=0.06, head_length=0.10',
                        color=cor, lw=0.6
                    ), zorder=3)
        txt  = f"L = {valor:.2f} m" if is_global else f"{valor:.2f} m"
        dy   = EXT_H * 1.1
        va   = 'bottom' if y_pos >= 0 else 'top'
        off  = dy if y_pos >= 0 else -dy
        ax.text((x_ini + x_fim)/2, y_pos + off, txt,
                color=COR_TXT if is_global else COR_TXT_DIM,
                fontsize=fs,
                fontweight='bold' if is_global else 'normal',
                ha='center', va=va, zorder=8,
                bbox=dict(boxstyle='round,pad=0.14', facecolor=COR_FUNDO,
                          edgecolor=cor, linewidth=0.4, alpha=0.82))

    # ── Coordenadas extremas visuais ──────────────────────────────────────
    x_vis_esq = mapa(0.0)
    x_vis_dir = mapa(total_real)

    # ── Lajes ─────────────────────────────────────────────────────────────
    if laje:
        for idx, (x0v, x1v) in enumerate(segmentos_lajes):
            draw_viga_seg(x0v, x1v, laje_seg=True)
            if idx == 0:
                draw_apoio(x0v, fix_xy=False)
                draw_rotula(x1v)
            else:
                draw_rotula(x0v)
                draw_apoio(x1v, fix_xy=False)
            draw_cota(x0v, x1v, float(laje), Y_DIM)

    # ── Vãos por tipologia ────────────────────────────────────────────────
    x_real_base = float(laje) if laje else 0.0

    if tipo_interno == "biapoiada":
        for i, (x0v, x1v) in enumerate(segmentos_vaos):
            draw_viga_seg(x0v, x1v)
            fix = (i == 0 and not laje)
            draw_apoio(x0v, fix_xy=fix)
            draw_apoio(x1v, fix_xy=False)
            draw_cota(x0v, x1v, vaos[i], Y_DIM)

    elif tipo_interno == "isostatica_em_balanco":
        vc, vb = vaos[0], vaos[1]
        x0 = mapa(x_real_base)
        x1 = mapa(x_real_base + vb)
        x2 = mapa(x_real_base + vb + vc)
        x3 = mapa(x_real_base + 2*vb + vc)
        draw_viga_seg(x0, x3)
        draw_apoio(x1, fix_xy=True)
        draw_apoio(x2, fix_xy=False)
        draw_cota(x0, x1, vb, Y_DIM)
        draw_cota(x1, x2, vc, Y_DIM)
        draw_cota(x2, x3, vb, Y_DIM)

    elif tipo_interno == "hiperestatica_sem_balanco":
        vc, ve = vaos[0], vaos[1]
        x0 = mapa(x_real_base)
        x1 = mapa(x_real_base + ve)
        x2 = mapa(x_real_base + ve + vc)
        x3 = mapa(x_real_base + 2*ve + vc)
        draw_viga_seg(x0, x3)
        draw_apoio(x0, fix_xy=True)
        for xp in (x1, x2, x3):
            draw_apoio(xp, fix_xy=False)
        draw_cota(x0, x1, ve, Y_DIM)
        draw_cota(x1, x2, vc, Y_DIM)
        draw_cota(x2, x3, ve, Y_DIM)

    elif tipo_interno == "hiperestatica_com_balanco":
        vc, ve, vb = vaos[0], vaos[1], vaos[2]
        reais = [
            x_real_base,
            x_real_base + vb,
            x_real_base + vb + ve,
            x_real_base + vb + ve + vc,
            x_real_base + vb + 2*ve + vc,
            x_real_base + 2*vb + 2*ve + vc,
        ]
        pts_vis = [mapa(r) for r in reais]
        draw_viga_seg(pts_vis[0], pts_vis[5])
        draw_apoio(pts_vis[1], fix_xy=True)
        for pv in pts_vis[2:5]:
            draw_apoio(pv, fix_xy=False)
        deltas = [vb, ve, vc, ve, vb]
        for i in range(5):
            draw_cota(pts_vis[i], pts_vis[i+1], deltas[i], Y_DIM)

    # ── Cota global ───────────────────────────────────────────────────────
    y_global = 0.75 * fator
    draw_cota(x_vis_esq, x_vis_dir, total_real, y_global, is_global=True)

    # ── Limites do painel ─────────────────────────────────────────────────
    pad       = 1.5 * fator
    x_vis_min = x_vis_esq - pad
    x_vis_max = x_vis_dir + pad
    ax.set_ylim(Y_DIM - 0.6*fator, y_global + 0.55*fator)
    ax.set_xlim(x_vis_min, x_vis_max)
    ax.set_aspect('equal')
    ax.axis('off')

    return x_vis_min, x_vis_max


# ============================================================================
# DESENHO DO GRÁFICO DE COEFICIENTE (PAINEL SUPERIOR)
# ============================================================================

def _desenhar_coef_em_axes(
    ax: plt.Axes,
    zonas: Dict[Tuple[float, float], float],
    mapa: Callable[[float], float],
    cor: str,
    x_limits: Tuple[float, float],
    tipo_coeficiente: str
) -> None:
    """
    Desenha o gráfico de degraus do coeficiente no eixo fornecido.

    Os limites X são sincronizados com os do painel DCL para garantir
    alinhamento visual perfeito.

    Parâmetros
    ----------
    ax : plt.Axes
        Eixo matplotlib onde o gráfico será desenhado.
    zonas : dict
        {(x_real_ini, x_real_fim): valor_coeficiente, ...}
    mapa : Callable
        Função de mapeamento real → visual.
    cor : str
        Cor principal dos degraus.
    x_limits : Tuple[float, float]
        Limites x visuais sincronizados com o DCL.
    tipo_coeficiente : str
        Chave para seleção do rótulo do eixo Y.
    """
    ax.set_facecolor(COR_FUNDO)
    ylabel = _ROTULOS_COEF.get(tipo_coeficiente, "Coeficiente (φ)")
    ax.set_ylabel(ylabel, color=COR_TXT, fontsize=9, labelpad=6)

    if not zonas:
        ax.text(0.5, 0.5, "Sem dados de coeficiente disponíveis",
                color=COR_TXT_DIM, ha="center", va="center",
                transform=ax.transAxes, fontsize=9)
        ax.set_xlim(x_limits)
        return

    # ── Transforma zonas para coordenadas visuais ──────────────────────────
    zonas_vis: Dict[Tuple[float, float], float] = {}
    for (xi, xf), val in zonas.items():
        xi_v = mapa(xi)
        xf_v = mapa(xf)
        if xi_v < xf_v:
            zonas_vis[(xi_v, xf_v)] = val

    if not zonas_vis:
        ax.text(0.5, 0.5, "Erro na transformação das zonas",
                color=COR_TXT_DIM, ha="center", va="center",
                transform=ax.transAxes, fontsize=9)
        ax.set_xlim(x_limits)
        return

    zonas_ord = sorted(zonas_vis.items())
    vals      = [v for _, v in zonas_ord]
    val_min   = min(vals)
    val_max   = max(vals)
    baseline  = 1.0

    # ── Limites Y com padding proporcional ───────────────────────────────
    y_pad = max(0.05, (val_max - val_min) * 0.30)
    y_low  = min(val_min, baseline) - y_pad * 0.20
    y_high = val_max + y_pad
    if y_high - y_low < 0.15:
        mid   = (y_high + y_low) / 2.0
        y_low  = mid - 0.10
        y_high = mid + 0.10

    x_total = (zonas_ord[-1][0][1] - zonas_ord[0][0][0]) or 1.0

    # ── Degraus ────────────────────────────────────────────────────────────
    for (xi, xf), val in zonas_ord:
        # Área preenchida (fill entre baseline e degrau)
        ax.fill_between([xi, xf], baseline, val,
                        color=cor, alpha=0.15, step=None, zorder=2)

        # Linha horizontal do degrau
        ax.plot([xi, xf], [val, val],
                color=cor, lw=2.5, solid_capstyle="butt", zorder=4)

        # Linhas verticais laterais do degrau
        for xp in (xi, xf):
            ax.plot([xp, xp], [baseline, val],
                    color=cor, lw=0.9, alpha=0.45, zorder=3)

        # Rótulo do valor (apenas se o degrau tiver largura suficiente)
        if (xf - xi) / x_total > 0.025:
            offset_txt = (y_high - y_low) * 0.045
            va_txt = "bottom" if val >= baseline else "top"
            dy_txt = offset_txt if val >= baseline else -offset_txt
            ax.text((xi + xf) / 2.0, val + dy_txt,
                    f"{val:.3f}",
                    color=COR_TXT, fontsize=7.5, ha="center",
                    va=va_txt, fontweight="bold", zorder=5)

    # Linha de baseline (referência = 1.0)
    if y_low <= baseline <= y_high:
        ax.axhline(baseline, color=COR_TXT_DIM, lw=0.7,
                   linestyle='--', alpha=0.35, zorder=1)
        ax.text(x_limits[0] + (x_limits[1]-x_limits[0]) * 0.01,
                baseline + (y_high-y_low)*0.02,
                "1.000", color=COR_TXT_DIM, fontsize=6.5, va='bottom')

    # ── Estilo dos eixos ───────────────────────────────────────────────────
    ax.set_ylim(y_low, y_high)
    ax.tick_params(colors=COR_TXT_DIM, labelsize=7.5)
    ax.tick_params(axis="x", labelbottom=False, length=0)
    ax.yaxis.grid(True, color=COR_GRID, lw=0.6, alpha=0.6)
    ax.set_axisbelow(True)
    for spine_name, spine in ax.spines.items():
        if spine_name == 'bottom':
            spine.set_visible(False)
        else:
            spine.set_edgecolor(COR_SPINE)

    ax.set_xlim(x_limits)
    ax.set_aspect('auto')


# ============================================================================
# FUNÇÃO PRINCIPAL PÚBLICA
# ============================================================================

def desenhar_figura_coeficiente(
    superestrutura: Superestrutura,
    coeficientes: Union["CoeficientesImpacto", Dict[Tuple[float, float], float]],
    material: str = "concreto_mista",
    tipo_coeficiente: str = "impacto"
) -> plt.Figure:
    """
    Gera a figura combinada: [coeficiente | DCL].

    Parâmetros
    ----------
    superestrutura : Superestrutura
        Objeto com geometria da ponte (tipo, vaos, laje_transicao).
    coeficientes : CoeficientesImpacto | dict
        Objeto com atributo ``zonas_impacto`` ou dicionário
        {(x_ini, x_fim): valor}.
    material : str
        Mantido para compatibilidade retroativa. Não utilizado.
    tipo_coeficiente : str
        Tipo de coeficiente a exibir. Valores:
        'impacto' | 'cia' | 'civ' | 'cnf'

    Retorna
    -------
    matplotlib.figure.Figure
        Figura 9.51 × 5.71 pol. a 100 DPI (951 × 571 px).
    """
    # ── Extrai zonas ──────────────────────────────────────────────────────
    if hasattr(coeficientes, 'zonas_impacto'):
        zonas: Dict = coeficientes.zonas_impacto
    elif isinstance(coeficientes, dict):
        zonas = coeficientes
    else:
        raise TypeError(
            "O parâmetro 'coeficientes' deve ser um CoeficientesImpacto, "
            "um dict ou objeto com atributo 'zonas_impacto'."
        )

    # ── Mapa visual ───────────────────────────────────────────────────────
    mapa, _, segmentos_vaos, segmentos_lajes = _criar_mapa_visual(superestrutura)

    # ── Figura principal (tamanho FIXO para QFrame) ───────────────────────
    fig = plt.figure(figsize=(9.51, 5.71), dpi=100, facecolor=COR_FUNDO)
    gs  = GridSpec(2, 1, figure=fig, height_ratios=[1.6, 1.0], hspace=0.0)
    ax_coef = fig.add_subplot(gs[0])
    ax_dcl  = fig.add_subplot(gs[1])

    # ── Painel inferior: DCL ──────────────────────────────────────────────
    x_vis_min, x_vis_max = _desenhar_dcl_em_axes(
        ax_dcl, superestrutura, mapa, segmentos_vaos, segmentos_lajes
    )

    # ── Painel superior: coeficiente ──────────────────────────────────────
    _desenhar_coef_em_axes(
        ax_coef, zonas, mapa,
        cor=COR_COEF,
        x_limits=(x_vis_min, x_vis_max),
        tipo_coeficiente=tipo_coeficiente
    )

    # ── Ajuste de layout ──────────────────────────────────────────────────
    plt.subplots_adjust(left=0.08, right=0.97, top=0.97, bottom=0.03)

    return fig


# ============================================================================
# BLOCO DE TESTES
# ============================================================================

if __name__ == "__main__":
    import matplotlib
    matplotlib.use("TkAgg")

    # Exemplo 1 – Biapoiada com 3 vãos
    print("Exemplo 1: Biapoiada – Coef. de Impacto")
    sup = Superestrutura(
        tipo="Isostática: Múltiplos Vãos Biapoioados",
        vaos=[6.0, 8.0, 5.0],
        laje_transicao=2.5
    )
    total = sum(sup.vaos) + 2 * sup.laje_transicao
    fig1  = desenhar_figura_coeficiente(
        sup, {(0.0, total): 1.35}, tipo_coeficiente="impacto"
    )
    plt.show()

    # Exemplo 2 – Hiperestática com balanço (CIA)
    print("Exemplo 2: Hiperestática c/ Balanço – CIA")
    sup2 = Superestrutura(
        tipo="Hiperestática: Vão Contínuo com Balanço",
        vaos=[30.0, 20.0, 3.0],
        laje_transicao=2.5
    )
    zonas2 = {
        (0.0, 10.0): 1.25,  (10.0, 20.0): 1.35, (20.0, 30.0): 1.30,
        (30.0, 40.0): 1.25, (40.0, 50.0): 1.15, (50.0, 60.0): 1.10,
        (60.0, 70.0): 1.05, (70.0, 78.0): 1.00,
    }
    fig2 = desenhar_figura_coeficiente(sup2, zonas2, tipo_coeficiente="cia")
    plt.show()

    # Exemplo 3 – Isostática em balanço (CIV)
    print("Exemplo 3: Isostática em Balanço – CIV")
    sup3 = Superestrutura(
        tipo="Isostática: Biapoiada com Balanço",
        vaos=[14.0, 5.0],
        laje_transicao=False
    )
    zonas3 = {(0.0, 5.0): 1.25, (5.0, 19.0): 1.35, (19.0, 24.0): 1.25}
    fig3   = desenhar_figura_coeficiente(sup3, zonas3, tipo_coeficiente="civ")
    plt.show()

    print("Testes concluídos.")
