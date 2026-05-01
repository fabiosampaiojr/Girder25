# ============================================================================
# desenho_dcl.py  |  BridgeCalc – Módulo de Desenho Técnico
# ============================================================================
# Descrição : Geração do Diagrama de Corpo Livre (DCL) para pontes e vigas.
#             Suporta quatro tipologias estruturais com escala visual
#             proporcional e padrão gráfico de desenho técnico de engenharia.
#
# Tipologias:
#   'biapoiada'                – N vãos independentes em série
#   'isostatica_em_balanco'    – 1 vão interno + 2 balanços simétricos
#   'hiperestatica_sem_balanco'– 1 vão central + 2 vãos laterais contínuos
#   'hiperestatica_com_balanco'– 1 vão central + 2 laterais + 2 balanços
#
# Parâmetro laje_transicao: float ou False  (lajes simétricas nas extremidades)
#
# Versão    : 2.0
# ============================================================================

import matplotlib
matplotlib.use('Agg')

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyArrowPatch
from typing import Union

# ─── PALETA DE CORES ────────────────────────────────────────────────────────
COR_FUNDO    = "#2b2b2b"   # fundo da figura
COR_VIGA     = "#e0e0e0"   # viga principal / linha de eixo
COR_VIGA_FG  = "#4a4a4a"   # fill interno da viga
COR_APOIO    = "#e0e0e0"   # apoios e rótulas
COR_SOLO     = "#e0e0e0"   # hachuras de solo
COR_DIM      = "#b0b0b0"   # linhas de cota
COR_TXT      = "#ffffff"   # texto geral
COR_TXT_DIM  = "#d0d0d0"   # texto de cota
COR_GLOBAL   = "#FFA726"   # destaque da cota global
COR_LAJE     = "#90CAF9"   # linha da laje de transição
COR_ROTULA   = "#e0e0e0"   # círculo de rótula


# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

def desenhar_dcl(
    tipo: str,
    vaos: list,
    laje_transicao: Union[float, bool] = False
) -> plt.Figure:
    """
    Gera o Diagrama de Corpo Livre (DCL) técnico para pontes e vigas.

    Parâmetros
    ----------
    tipo : str
        Tipologia estrutural. Valores aceitos:
        - 'biapoiada'
        - 'isostatica_em_balanco'
        - 'hiperestatica_sem_balanco'
        - 'hiperestatica_com_balanco'
    vaos : list
        Comprimentos em metros conforme a tipologia:
        - biapoiada                 → [v1, v2, ..., vN]
        - isostatica_em_balanco     → [v_interno, v_balanco]
        - hiperestatica_sem_balanco → [v_central, v_extremidade]
        - hiperestatica_com_balanco → [v_central, v_extremidade, v_balanco]
    laje_transicao : float | False
        Comprimento da laje de transição. Aplicada simetricamente em ambas
        as extremidades quando fornecida.

    Retorna
    -------
    matplotlib.figure.Figure
        Figura gerada, pronta para exibição em QFrame ou exportação.
    """

    # ── 1. CÁLCULO DA EXTENSÃO TOTAL E FATOR DE ESCALA ───────────────────────
    _REFERENCIA_M = 20.0   # comprimento de referência para normalização visual

    if tipo == 'isostatica_em_balanco':
        soma_vaos = vaos[0] + 2.0 * vaos[1]
    elif tipo == 'hiperestatica_sem_balanco':
        soma_vaos = vaos[0] + 2.0 * vaos[1]
    elif tipo == 'hiperestatica_com_balanco':
        soma_vaos = vaos[0] + 2.0 * vaos[1] + 2.0 * vaos[2]
    else:  # biapoiada
        soma_vaos = sum(vaos)

    soma_lajes  = (2.0 * laje_transicao) if laje_transicao else 0.0
    total_real  = soma_vaos + soma_lajes
    fator       = max(0.5, total_real / _REFERENCIA_M)

    # ── 2. CONSTANTES GEOMÉTRICAS ESCALADAS ───────────────────────────────────
    VIGA_H      = 0.22  * fator   # espessura da viga (retângulo)
    VIGA_Y_TOP  = 0.0              # topo da viga (referência)
    VIGA_Y_BOT  = -VIGA_H         # base da viga

    LAP         = 0.60  * fator   # lado do triângulo de apoio
    R_ROT       = 0.12  * fator   # raio da rótula
    GAP_VIS     = LAP + 0.15 * fator  # gap visual entre vãos biapoiados
    Y_SOLO      = VIGA_Y_BOT - LAP - 0.20 * fator  # y da linha de solo
    N_HACH      = 6                # número de hachuras no apoio fixo

    OFF_COTA    = 1.50  * fator   # distância das cotas abaixo da base
    Y_DIM_INF   = VIGA_Y_BOT - OFF_COTA  # y das cotas inferiores
    Y_DIM_SUP   = VIGA_Y_TOP  + 0.85 * fator  # y da cota global superior
    EXT_LINE_H  = 0.12  * fator   # comprimento das linhas de extensão
    FS_DIM      = max(6.5, 9.0 - fator * 0.4)  # fontsize das cotas (diminui p/ pontes grandes)
    FS_GLOBAL   = FS_DIM + 1.0

    # ── 3. FIGURA ─────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(12, 4), facecolor=COR_FUNDO)
    ax.set_facecolor(COR_FUNDO)

    # ── 4. FUNÇÕES AUXILIARES DE DESENHO ─────────────────────────────────────

    def draw_viga(x_ini: float, x_fim: float, cor_linha=COR_VIGA, lw=1.8, laje=False):
        """Desenha a viga como retângulo técnico com borda e preenchimento."""
        cor_fill = "#3a6186" if laje else COR_VIGA_FG
        cor_edge = COR_LAJE if laje else cor_linha
        ax.add_patch(patches.FancyBboxPatch(
            (x_ini, VIGA_Y_BOT), x_fim - x_ini, VIGA_H,
            boxstyle="square,pad=0",
            facecolor=cor_fill, edgecolor=cor_edge, lw=lw, zorder=2
        ))

    def draw_apoio(x: float, fix_xy: bool = False):
        """
        Desenha apoio de 1.º gênero (rolo – fix_xy=False) ou
        2.º gênero (fixo – fix_xy=True).
        O triângulo tem o vértice superior tangente à base da viga.
        """
        apex_y = VIGA_Y_BOT
        # Triângulo
        pts = np.array([
            [x,           apex_y],
            [x - LAP/2,   Y_SOLO + 0.20 * fator],
            [x + LAP/2,   Y_SOLO + 0.20 * fator],
        ])
        ax.add_patch(patches.Polygon(
            pts, closed=True,
            edgecolor=COR_APOIO, facecolor='none', lw=1.3, zorder=4
        ))

        # Linha de solo
        y_base = Y_SOLO + 0.20 * fator
        ax.plot([x - LAP/2, x + LAP/2], [y_base, y_base],
                color=COR_SOLO, lw=1.3, zorder=4)

        if fix_xy:
            # Hachura: apoio engastado em X e Y
            dy_hach = 0.24 * fator
            dx_hach = 0.16 * fator
            for xi in np.linspace(x - LAP/2, x + LAP/2, N_HACH):
                ax.plot([xi, xi - dx_hach], [y_base, y_base - dy_hach],
                        color=COR_SOLO, lw=0.9, zorder=3)
        else:
            # Rolo: linha dupla → liberdade de translação horizontal
            y_rolo = y_base - 0.16 * fator
            ax.plot([x - LAP/2, x + LAP/2], [y_rolo, y_rolo],
                    color=COR_SOLO, lw=1.3, zorder=4)
            # Pequenas bolinhas representando roletes (estética)
            n_rolo = 3
            for xr in np.linspace(x - LAP/2 + LAP/8, x + LAP/2 - LAP/8, n_rolo):
                ax.add_patch(patches.Circle(
                    (xr, y_base - 0.08 * fator), 0.04 * fator,
                    facecolor=COR_SOLO, edgecolor='none', zorder=5
                ))

    def draw_rotula(x: float):
        """Desenha rótula de junta com círculo e ponto central."""
        ax.add_patch(patches.Circle(
            (x, VIGA_Y_BOT), R_ROT,
            edgecolor=COR_ROTULA, facecolor=COR_FUNDO,
            lw=1.3, zorder=6
        ))
        ax.add_patch(patches.Circle(
            (x, VIGA_Y_BOT), R_ROT * 0.3,
            facecolor=COR_ROTULA, edgecolor='none',
            zorder=7
        ))

    def draw_cota(x_ini: float, x_fim: float, valor: float,
                  y_pos: float, is_global: bool = False):
        """
        Desenha cota técnica com:
         - Linhas de extensão verticais
         - Seta bidirecional horizontal
         - Texto centralizado com fundo
        """
        cor  = COR_GLOBAL if is_global else COR_DIM
        fs   = FS_GLOBAL  if is_global else FS_DIM
        lw   = 1.0        if is_global else 0.7

        # Linhas de extensão (perpendiculares à linha de cota)
        for xp in (x_ini, x_fim):
            ax.plot([xp, xp],
                    [y_pos + EXT_LINE_H, y_pos - EXT_LINE_H],
                    color=cor, lw=lw, zorder=3)

        # Seta bidirecional
        ax.annotate(
            '', xy=(x_ini, y_pos), xytext=(x_fim, y_pos),
            arrowprops=dict(
                arrowstyle='<->, head_width=0.10, head_length=0.18',
                color=cor, lw=lw
            ),
            zorder=3
        )

        # Texto
        txt = f"L = {valor:.2f} m" if is_global else f"{valor:.2f} m"
        dy  = EXT_LINE_H * 1.1
        va  = 'bottom' if y_pos >= 0 else 'top'
        off = dy if y_pos >= 0 else -dy

        ax.text(
            (x_ini + x_fim) / 2, y_pos + off, txt,
            color=COR_TXT if is_global else COR_TXT_DIM,
            fontsize=fs, fontweight='bold' if is_global else 'normal',
            ha='center', va=va, zorder=8,
            bbox=dict(
                boxstyle='round,pad=0.18',
                facecolor=COR_FUNDO,
                edgecolor=cor,
                linewidth=0.5,
                alpha=0.85
            )
        )

    # ── 5. MONTAGEM DAS COORDENADAS E DESENHO ─────────────────────────────────
    x_cursor   = 0.0
    x_viga_ini = 0.0

    # --- Laje de transição (esquerda) ---
    if laje_transicao:
        draw_viga(0.0, laje_transicao, laje=True)
        draw_rotula(laje_transicao)
        draw_apoio(0.0, fix_xy=False)
        draw_cota(0.0, laje_transicao, laje_transicao, Y_DIM_INF)
        x_cursor = laje_transicao

    x_viga_ini = x_cursor

    # --- Vãos por tipologia ---
    if tipo == 'biapoiada':
        for i, vao in enumerate(vaos):
            x_fim = x_cursor + vao
            draw_viga(x_cursor, x_fim)
            draw_apoio(x_cursor, fix_xy=(i == 0))
            draw_apoio(x_fim,    fix_xy=False)
            draw_cota(x_cursor, x_fim, vao, Y_DIM_INF)
            x_cursor = x_fim + GAP_VIS
        x_viga_fim = x_cursor - GAP_VIS

    elif tipo == 'isostatica_em_balanco':
        v_int, v_bal = vaos[0], vaos[1]
        pts = [
            x_viga_ini,
            x_viga_ini + v_bal,
            x_viga_ini + v_bal + v_int,
            x_viga_ini + 2 * v_bal + v_int,
        ]
        draw_viga(pts[0], pts[3])
        draw_apoio(pts[1], fix_xy=True)
        draw_apoio(pts[2], fix_xy=False)
        draw_cota(pts[0], pts[1], v_bal, Y_DIM_INF)
        draw_cota(pts[1], pts[2], v_int, Y_DIM_INF)
        draw_cota(pts[2], pts[3], v_bal, Y_DIM_INF)
        x_viga_fim = pts[3]

    elif tipo == 'hiperestatica_sem_balanco':
        v_c, v_e = vaos[0], vaos[1]
        pts = [
            x_viga_ini,
            x_viga_ini + v_e,
            x_viga_ini + v_e + v_c,
            x_viga_ini + 2 * v_e + v_c,
        ]
        draw_viga(pts[0], pts[3])
        draw_apoio(pts[0], fix_xy=True)
        draw_apoio(pts[1], fix_xy=False)
        draw_apoio(pts[2], fix_xy=False)
        draw_apoio(pts[3], fix_xy=False)
        draw_cota(pts[0], pts[1], v_e, Y_DIM_INF)
        draw_cota(pts[1], pts[2], v_c, Y_DIM_INF)
        draw_cota(pts[2], pts[3], v_e, Y_DIM_INF)
        x_viga_fim = pts[3]

    elif tipo == 'hiperestatica_com_balanco':
        v_c, v_e, v_b = vaos[0], vaos[1], vaos[2]
        pts = [
            x_viga_ini,
            x_viga_ini + v_b,
            x_viga_ini + v_b + v_e,
            x_viga_ini + v_b + v_e + v_c,
            x_viga_ini + v_b + 2 * v_e + v_c,
            x_viga_ini + 2 * v_b + 2 * v_e + v_c,
        ]
        draw_viga(pts[0], pts[5])
        draw_apoio(pts[1], fix_xy=True)
        for p in pts[2:5]:
            draw_apoio(p, fix_xy=False)
        draw_cota(pts[0], pts[1], v_b, Y_DIM_INF)
        draw_cota(pts[1], pts[2], v_e, Y_DIM_INF)
        draw_cota(pts[2], pts[3], v_c, Y_DIM_INF)
        draw_cota(pts[3], pts[4], v_e, Y_DIM_INF)
        draw_cota(pts[4], pts[5], v_b, Y_DIM_INF)
        x_viga_fim = pts[5]

    else:
        raise ValueError(f"Tipo de estrutura desconhecido: '{tipo}'")

    # --- Laje de transição (direita) ---
    if laje_transicao:
        draw_viga(x_viga_fim, x_viga_fim + laje_transicao, laje=True)
        draw_rotula(x_viga_fim)
        draw_apoio(x_viga_fim + laje_transicao, fix_xy=False)
        draw_cota(x_viga_fim, x_viga_fim + laje_transicao, laje_transicao, Y_DIM_INF)
        x_viga_fim += laje_transicao

    # ── 6. COTA GLOBAL ────────────────────────────────────────────────────────
    draw_cota(0.0, x_viga_fim, total_real, Y_DIM_SUP, is_global=True)

    # ── 7. LINHA DE EIXO (traço-ponto) ───────────────────────────────────────
    ax.plot([0.0, x_viga_fim], [VIGA_Y_TOP, VIGA_Y_TOP],
            color=COR_GLOBAL, lw=0.5, linestyle=(0, (6, 4, 1, 4)),
            alpha=0.35, zorder=1)

    # ── 8. ENQUADRAMENTO ──────────────────────────────────────────────────────
    pad_x = 1.8 * fator
    ax.set_xlim(-pad_x, x_viga_fim + pad_x)
    ax.set_ylim(Y_DIM_INF - 0.8 * fator, Y_DIM_SUP + 0.8 * fator)
    ax.set_aspect('equal')
    ax.axis('off')
    plt.subplots_adjust(left=0.01, right=0.99, top=0.95, bottom=0.05)

    return fig


# ============================================================================
# BLOCO DE TESTES
# ============================================================================

if __name__ == "__main__":
    import matplotlib
    matplotlib.use('TkAgg')

    casos = [
        dict(tipo='hiperestatica_com_balanco', vaos=[30.0, 20.0, 3.0], laje_transicao=0,
             titulo="Hiperestática c/ Balanço (86 m)"),
        dict(tipo='isostatica_em_balanco',     vaos=[14.0, 5.0],        laje_transicao=3.0,
             titulo="Isostática em Balanço c/ Lajes (30 m)"),
        dict(tipo='hiperestatica_sem_balanco', vaos=[20.0, 12.0],       laje_transicao=0,
             titulo="Hiperestática s/ Balanço (44 m)"),
        dict(tipo='biapoiada',                 vaos=[6.0, 6.0],         laje_transicao=False,
             titulo="Biapoiada (12 m)"),
    ]

    for caso in casos:
        titulo = caso.pop('titulo')
        fig = desenhar_dcl(**caso)
        ax  = fig.axes[0]
        ax.set_title(titulo, color='white', fontsize=10, pad=4)
        plt.show()
        caso['titulo'] = titulo  # restaura para eventual re-uso
