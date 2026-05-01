# ============================================================================
# desenho_ponte_carregada.py  |  BridgeCalc – Módulo de Desenho Técnico
# ============================================================================
# Descrição : Gera o DCL completo integrando geometria estrutural e
#             carregamentos (distribuídos e concentrados) aplicados à ponte.
#
# Tamanho   : figsize=(9.61, 4.81), dpi=100 – FIXO para QFrame da UI.
#
# Tipologias suportadas: biapoiada, isostatica_em_balanco,
#   hiperestatica_sem_balanco, hiperestatica_com_balanco.
#
# Parâmetro acoes (dict opcional):
#   "Carga Distribuída"  : list[ [valor_kN_m, x_ini, x_fim], ... ]
#   "Carga Concentrada"  : list[ [valor_kN,   x1, x2, ...], ... ]
#   As coordenadas x são fornecidas em metros, no sistema real da viga.
#
# Versão    : 2.0
# ============================================================================

import matplotlib
matplotlib.use('Agg')

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from typing import Union, Optional

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
COR_DIST     = "#90CAF9"    # cargas distribuídas
COR_CONC     = "#EF9A9A"    # cargas concentradas
COR_GLOBAL   = "#FFA726"    # cota global


# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

def desenhar_ponte_carregada(
    tipo: str,
    vaos: list,
    laje_transicao: Union[float, int] = 0,
    acoes: Optional[dict] = None
) -> plt.Figure:
    """
    Gera o DCL completo com geometria estrutural e carregamentos.

    Parâmetros
    ----------
    tipo : str
        Tipologia estrutural:
        'biapoiada' | 'isostatica_em_balanco' |
        'hiperestatica_sem_balanco' | 'hiperestatica_com_balanco'
    vaos : list
        Comprimentos em metros conforme a tipologia.
    laje_transicao : float
        Comprimento da laje de transição (0 = sem laje).
    acoes : dict, opcional
        Dicionário de carregamentos:
        {
          "Carga Distribuída": [[valor_kN_m, x_ini, x_fim], ...],
          "Carga Concentrada": [[valor_kN, x1, x2, ...], ...]
        }

    Retorna
    -------
    matplotlib.figure.Figure
        Figura 9.61 × 4.81 pol. a 100 DPI.
    """

    # ── 1. EXTENSÃO TOTAL E FATOR DE ESCALA ───────────────────────────────────
    if tipo in ('isostatica_em_balanco', 'hiperestatica_sem_balanco'):
        soma_vaos = vaos[0] + 2.0 * vaos[1]
    elif tipo == 'hiperestatica_com_balanco':
        soma_vaos = vaos[0] + 2.0 * vaos[1] + 2.0 * vaos[2]
    else:
        soma_vaos = sum(vaos)

    soma_lajes  = 2.0 * laje_transicao if laje_transicao else 0.0
    total_real  = soma_vaos + soma_lajes
    fator       = max(0.5, total_real / 20.0)

    # ── 2. CONSTANTES GEOMÉTRICAS ─────────────────────────────────────────────
    VIGA_H      = 0.22  * fator
    VIGA_Y_TOP  = 0.0
    VIGA_Y_BOT  = -VIGA_H

    LAP         = 0.55  * fator
    R_ROT       = 0.10  * fator
    GAP_VIS     = LAP   + 0.15 * fator
    Y_SOLO      = VIGA_Y_BOT - LAP - 0.20 * fator
    N_HACH      = 6

    OFF_COTA    = 1.35  * fator
    Y_DIM_INF   = VIGA_Y_BOT - OFF_COTA
    EXT_H       = 0.10  * fator
    FS_DIM      = max(5.5, 8.0 - fator * 0.35)

    # Cargas: alturas base
    H_DIST_MAX  = 1.20  * fator   # altura máxima das setas distribuídas
    H_DIST_MIN  = 0.32  * fator   # altura mínima (proporcional)
    H_CONC      = 1.60  * fator   # altura fixa das cargas concentradas

    # ── 3. FIGURA ─────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(9.61, 4.81), dpi=100, facecolor=COR_FUNDO)
    ax.set_facecolor(COR_FUNDO)

    # ── 4. FUNÇÕES AUXILIARES ─────────────────────────────────────────────────

    def draw_viga(x_ini: float, x_fim: float, laje: bool = False):
        cor_fg = COR_LAJE_FG if laje else COR_VIGA_FG
        cor_ed = COR_LAJE_ED if laje else COR_VIGA
        ax.add_patch(patches.FancyBboxPatch(
            (x_ini, VIGA_Y_BOT), x_fim - x_ini, VIGA_H,
            boxstyle="square,pad=0",
            facecolor=cor_fg, edgecolor=cor_ed, lw=1.3, zorder=2
        ))

    def draw_apoio(x: float, fix_xy: bool = False):
        apex_y  = VIGA_Y_BOT
        y_base  = Y_SOLO + 0.20 * fator
        pts = np.array([
            [x,          apex_y],
            [x - LAP/2,  y_base],
            [x + LAP/2,  y_base],
        ])
        ax.add_patch(patches.Polygon(
            pts, closed=True,
            edgecolor=COR_APOIO, facecolor='none', lw=1.2, zorder=4
        ))
        ax.plot([x - LAP/2, x + LAP/2], [y_base, y_base],
                color=COR_APOIO, lw=1.2, zorder=4)
        if fix_xy:
            dy = 0.22 * fator
            dx = 0.15 * fator
            for xi in np.linspace(x - LAP/2, x + LAP/2, N_HACH):
                ax.plot([xi, xi - dx], [y_base, y_base - dy],
                        color=COR_APOIO, lw=0.8, zorder=3)
        else:
            y_rolo = y_base - 0.15 * fator
            ax.plot([x - LAP/2, x + LAP/2], [y_rolo, y_rolo],
                    color=COR_APOIO, lw=1.2, zorder=4)
            for xr in np.linspace(x - LAP/2 + LAP/8, x + LAP/2 - LAP/8, 3):
                ax.add_patch(patches.Circle(
                    (xr, y_base - 0.075 * fator), 0.035 * fator,
                    facecolor=COR_APOIO, edgecolor='none', zorder=5
                ))

    def draw_rotula(x: float):
        ax.add_patch(patches.Circle(
            (x, VIGA_Y_BOT), R_ROT,
            edgecolor=COR_ROTULA, facecolor=COR_FUNDO, lw=1.2, zorder=6
        ))
        ax.add_patch(patches.Circle(
            (x, VIGA_Y_BOT), R_ROT * 0.3,
            facecolor=COR_ROTULA, edgecolor='none', zorder=7
        ))

    def draw_cota(x_ini: float, x_fim: float, valor: float, y_pos: float):
        for xp in (x_ini, x_fim):
            ax.plot([xp, xp], [y_pos + EXT_H, y_pos - EXT_H],
                    color=COR_DIM, lw=0.6, zorder=3)
        ax.annotate('', xy=(x_ini, y_pos), xytext=(x_fim, y_pos),
                    arrowprops=dict(
                        arrowstyle='<->, head_width=0.07, head_length=0.12',
                        color=COR_DIM, lw=0.6
                    ), zorder=3)
        ax.text((x_ini + x_fim) / 2, y_pos - EXT_H * 1.1,
                f"{valor:.2f} m", color=COR_TXT_DIM,
                fontsize=FS_DIM, ha='center', va='top',
                bbox=dict(boxstyle='round,pad=0.15',
                          facecolor=COR_FUNDO, edgecolor=COR_DIM,
                          linewidth=0.4, alpha=0.80))

    # ── 5. MONTAGEM DA ESTRUTURA ───────────────────────────────────────────────
    x_cursor = 0.0

    if laje_transicao:
        draw_viga(0.0, laje_transicao, laje=True)
        draw_rotula(laje_transicao)
        draw_apoio(0.0, fix_xy=False)
        draw_cota(0.0, laje_transicao, laje_transicao, Y_DIM_INF)
        x_cursor = laje_transicao

    x_viga_ini = x_cursor

    if tipo == 'biapoiada':
        for i, vao in enumerate(vaos):
            x_fim = x_cursor + vao
            draw_viga(x_cursor, x_fim)
            draw_apoio(x_cursor, fix_xy=(i == 0))
            draw_apoio(x_fim, fix_xy=False)
            draw_cota(x_cursor, x_fim, vao, Y_DIM_INF)
            x_cursor = x_fim + GAP_VIS
        x_viga_fim = x_cursor - GAP_VIS

    elif tipo == 'isostatica_em_balanco':
        v_int, v_bal = vaos[0], vaos[1]
        pts = [x_viga_ini,
               x_viga_ini + v_bal,
               x_viga_ini + v_bal + v_int,
               x_viga_ini + 2 * v_bal + v_int]
        draw_viga(pts[0], pts[3])
        draw_apoio(pts[1], fix_xy=True)
        draw_apoio(pts[2], fix_xy=False)
        draw_cota(pts[0], pts[1], v_bal, Y_DIM_INF)
        draw_cota(pts[1], pts[2], v_int, Y_DIM_INF)
        draw_cota(pts[2], pts[3], v_bal, Y_DIM_INF)
        x_viga_fim = pts[3]

    elif tipo == 'hiperestatica_sem_balanco':
        v_c, v_e = vaos[0], vaos[1]
        pts = [x_viga_ini,
               x_viga_ini + v_e,
               x_viga_ini + v_e + v_c,
               x_viga_ini + 2 * v_e + v_c]
        draw_viga(pts[0], pts[3])
        draw_apoio(pts[0], fix_xy=True)
        for p in pts[1:]:
            draw_apoio(p, fix_xy=False)
        draw_cota(pts[0], pts[1], v_e, Y_DIM_INF)
        draw_cota(pts[1], pts[2], v_c, Y_DIM_INF)
        draw_cota(pts[2], pts[3], v_e, Y_DIM_INF)
        x_viga_fim = pts[3]

    elif tipo == 'hiperestatica_com_balanco':
        v_c, v_e, v_b = vaos[0], vaos[1], vaos[2]
        pts = [x_viga_ini,
               x_viga_ini + v_b,
               x_viga_ini + v_b + v_e,
               x_viga_ini + v_b + v_e + v_c,
               x_viga_ini + v_b + 2 * v_e + v_c,
               x_viga_ini + 2 * v_b + 2 * v_e + v_c]
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
        raise ValueError(f"Tipologia desconhecida: '{tipo}'")

    if laje_transicao:
        draw_viga(x_viga_fim, x_viga_fim + laje_transicao, laje=True)
        draw_rotula(x_viga_fim)
        draw_apoio(x_viga_fim + laje_transicao, fix_xy=False)
        draw_cota(x_viga_fim, x_viga_fim + laje_transicao, laje_transicao, Y_DIM_INF)
        x_viga_fim += laje_transicao

    # ── 6. CARREGAMENTOS ───────────────────────────────────────────────────────
    if acoes:

        # --- Cargas distribuídas ---
        dist_loads = acoes.get("Carga Distribuída", [])
        if dist_loads:
            valores = [c[0] for c in dist_loads]
            v_max   = max(valores)
            v_min   = min(valores)
            span    = v_max - v_min if v_max != v_min else 1.0

            for carga in dist_loads:
                valor, x_ini, x_fim = carga[0], carga[1], carga[2]
                escala  = (valor - v_min) / span if span > 0 else 0.5
                h_dist  = H_DIST_MIN + escala * (H_DIST_MAX - H_DIST_MIN)

                # Preenchimento semi-transparente
                xs_fill = np.linspace(x_ini, x_fim, 60)
                ax.fill_between(xs_fill, VIGA_Y_TOP, h_dist,
                                color=COR_DIST, alpha=0.10, zorder=1)

                # Linha superior
                ax.plot([x_ini, x_fim], [h_dist, h_dist],
                        color=COR_DIST, lw=1.1, zorder=3)

                # Setas verticais
                n_setas = max(3, int((x_fim - x_ini) / (0.50 * fator)))
                for xs in np.linspace(x_ini, x_fim, n_setas):
                    ax.annotate('', xy=(xs, VIGA_Y_TOP),
                                xytext=(xs, h_dist),
                                arrowprops=dict(arrowstyle='-|>',
                                                color=COR_DIST, lw=0.55,
                                                mutation_scale=4.5),
                                zorder=2)

                # Etiqueta
                ax.text((x_ini + x_fim) / 2, h_dist + 0.08 * fator,
                        f"{valor} kN/m", color=COR_TXT,
                        ha='center', va='bottom',
                        fontsize=max(5.0, FS_DIM - 0.5), fontweight='bold',
                        bbox=dict(boxstyle='round,pad=0.18',
                                  facecolor='#383838', edgecolor=COR_DIST,
                                  linewidth=0.5, alpha=0.92),
                        zorder=8)

        # --- Cargas concentradas (soma por ponto) ---
        conc_loads = acoes.get("Carga Concentrada", [])
        if conc_loads:
            soma_por_x: dict = {}
            for carga in conc_loads:
                valor = carga[0]
                for xc in carga[1:]:
                    soma_por_x[xc] = soma_por_x.get(xc, 0.0) + valor

            for xc, total in soma_por_x.items():
                ax.annotate('',
                            xy=(xc, VIGA_Y_TOP + 0.03 * fator),
                            xytext=(xc, H_CONC),
                            arrowprops=dict(arrowstyle='-|>',
                                            color=COR_CONC, lw=1.6,
                                            mutation_scale=12),
                            zorder=5)
                # Linha vertical de chamada (tracejado sutil)
                ax.plot([xc, xc], [VIGA_Y_TOP, H_CONC],
                        color=COR_CONC, lw=0.4, linestyle='--', alpha=0.3, zorder=1)
                ax.text(xc, H_CONC + 0.08 * fator,
                        f"{total:.0f} kN", color=COR_TXT,
                        ha='center', va='bottom',
                        fontsize=max(5.0, FS_DIM - 0.5), fontweight='bold',
                        bbox=dict(boxstyle='round,pad=0.18',
                                  facecolor='#383838', edgecolor=COR_CONC,
                                  linewidth=0.5, alpha=0.92),
                        zorder=8)

    # ── 7. ENQUADRAMENTO ──────────────────────────────────────────────────────
    pad_x = 1.5 * fator
    ax.set_xlim(-pad_x, x_viga_fim + pad_x)
    ax.set_ylim(Y_DIM_INF - 0.6 * fator, H_CONC + 0.8 * fator)
    ax.set_aspect('equal')
    ax.axis('off')
    plt.subplots_adjust(left=0.01, right=0.99, top=0.97, bottom=0.03)

    return fig


# ============================================================================
# BLOCO DE TESTES
# ============================================================================

if __name__ == "__main__":
    import matplotlib
    matplotlib.use('TkAgg')

    acoes_teste = {
        "Carga Concentrada": [[450.0, 12.0, 18.0]],
        "Carga Distribuída":  [[15.0, 0.0, 10.0], [5.0, 20.0, 30.0]],
    }

    fig = desenhar_ponte_carregada(
        tipo='isostatica_em_balanco',
        vaos=[14.0, 5.0],
        laje_transicao=3.0,
        acoes=acoes_teste
    )
    plt.show()
