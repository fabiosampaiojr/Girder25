# ============================================================================
# desenho_sec_transversal.py  |  BridgeCalc – Módulo de Desenho Técnico
# ============================================================================
# Descrição : Gera o desenho técnico da seção transversal de tabuleiros de
#             pontes rodoviárias, segundo NBR 7188 / DNIT.
#
# Para classes com pista dupla, representa o tabuleiro da esquerda.
# Composição (esq → dir):
#   Pista Dupla : [passeio] + NJ + AI + 2F + AE + NJ + [passeio]
#   Pista Simples: [passeio] + NJ + AE + 2F + AE + NJ + [passeio]
#
# Legenda de símbolos:
#   NJ  – Barreira New Jersey           F  – Faixa de rolamento
#   AI  – Acostamento interno           AE – Acostamento externo
#
# Versão    : 2.1  (suporte a classe Personalizado)
# ============================================================================

import matplotlib
matplotlib.use('Agg')

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import Polygon
from typing import Union

# ─── PALETA DE CORES ────────────────────────────────────────────────────────
COR_FUNDO    = "#2b2b2b"
COR_TXT      = "#ffffff"
COR_DIM      = "#b0b0b0"
COR_TXT_DIM  = "#cccccc"
COR_ASFALTO  = "#3c3c3c"   # revestimento asfáltico
COR_CONCRETO = "#9e9e9e"   # estrutura de concreto (NJ / guia)
COR_CONC_ED  = "#e0e0e0"   # borda do concreto
COR_HACH     = "#6e6e6e"   # hachura de concreto
COR_LINHA    = "#e0e0e0"   # linha de base
COR_COMP     = "#90CAF9"   # linha de cota de componentes
COR_GLOBAL   = "#FFA726"   # destaque da largura total

# ─── TABELA DE CLASSES (NBR 7188 / DNIT) ─────────────────────────────────────
# Dimensões em centímetros: faixa(f), acostamento externo(ac_ext),
# acostamento interno(ac_int). pista_dupla indica se o tabuleiro é de
# pista dupla (True) ou simples (False).
MAPA_CLASSES: dict = {
    "0":     {"faixa": 375, "ac_ext": 300, "ac_int": 60,  "pista_dupla": True},
    "I - A": {"faixa": 360, "ac_ext": 300, "ac_int": 60,  "pista_dupla": True},
    "I - B": {"faixa": 350, "ac_ext": 250, "ac_int": 0,   "pista_dupla": False},
    "II":    {"faixa": 350, "ac_ext": 250, "ac_int": 0,   "pista_dupla": False},
    "III":   {"faixa": 350, "ac_ext": 150, "ac_int": 0,   "pista_dupla": False},
    "IV":    {"faixa": 300, "ac_ext": 150, "ac_int": 0,   "pista_dupla": False},
}

# Dimensões da barreira New Jersey (em cm)
NJ_LARG      = 40    # largura total da base
NJ_ALTO      = 87    # altura total
NJ_DEGRAU_H  = 15    # altura do degrau inferior
NJ_CURVA_Y1  = 40    # y do início do topo inclinado
NJ_CURVA_X1  = 22.5  # x do início do topo inclinado
NJ_TOPO_X    = 17.5  # x do topo da barreira

# Largura do guia de calçada (passeio)
GUIA_LARG    = 15
GUIA_ALTO    = 90

FS_COTA  = 8.0
FS_COMP  = 8.0
FS_TOTAL = 10.0


# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

def desenhar_sec_transversal(
    classe: str,
    h_borda: float,
    h_centro: float,
    passeio: Union[float, bool] = False,
    config_personalizado: dict = None   # NOVO: dimensões da classe Personalizado
) -> plt.Figure:
    """
    Gera o desenho técnico da seção transversal do tabuleiro.

    Parâmetros
    ----------
    classe : str
        Classe da rodovia. Valores válidos: '0', 'I - A', 'I - B',
        'II', 'III', 'IV', 'Personalizado'.
    h_borda : float
        Espessura do pavimento asfáltico na borda [cm].
    h_centro : float
        Espessura do pavimento asfáltico no centro (abaulamento) [cm].
    passeio : float | False
        Largura do passeio lateral [cm]. False = sem passeio.
    config_personalizado : dict, opcional
        Necessário apenas quando classe == "Personalizado".
        Deve conter chaves: 'faixa', 'ac_ext', 'ac_int', 'pista_dupla'.

    Retorna
    -------
    matplotlib.figure.Figure
    """

    # ── 0. FALLBACK PARA CLASSE PERSONALIZADA ────────────────────────────────
    if classe == "Personalizado":
        if config_personalizado is None:
            return None   # sem dados, não há como desenhar
        # Extrai as dimensões do dicionário personalizado
        f     = config_personalizado["faixa"]
        ae    = config_personalizado["ac_ext"]
        ai    = config_personalizado["ac_int"]
        dupla = config_personalizado["pista_dupla"]
    else:
        config = MAPA_CLASSES.get(classe)
        if config is None:
            raise ValueError(
                f"Classe '{classe}' não reconhecida. "
                f"Valores válidos: {list(MAPA_CLASSES.keys())}"
            )
        f     = config["faixa"]
        ae    = config["ac_ext"]
        ai    = config["ac_int"]
        dupla = config["pista_dupla"]

    p    = float(passeio) if passeio else 0.0

    # ── 2. CÁLCULO DAS POSIÇÕES X ─────────────────────────────────────────────
    x0 = 0.0

    # Guia de passeio (esquerda)
    x_guia_esq_ini = x0
    x_guia_esq_fim = x_guia_esq_ini + (GUIA_LARG if p > 0 else 0)

    # Passeio propriamente dito
    x_passeio_esq_ini = x_guia_esq_fim
    x_passeio_esq_fim = x_passeio_esq_ini + (p - GUIA_LARG if p > GUIA_LARG else 0)

    # Face interna da NJ esquerda
    x_nj_esq_ini = x_passeio_esq_fim if p > 0 else x0
    x_nj_esq_fim = x_nj_esq_ini + NJ_LARG

    # Miolo da pista
    larg_pista = (ai + 2 * f + ae) if dupla else (2 * ae + 2 * f)
    x_pista_ini = x_nj_esq_fim
    x_pista_fim = x_pista_ini + larg_pista

    # NJ direita
    x_nj_dir_ini = x_pista_fim
    x_nj_dir_fim = x_nj_dir_ini + NJ_LARG

    # Passeio e guia (direita) – somente pista simples
    x_fim_absoluto = x_nj_dir_fim
    if p > 0 and not dupla:
        x_fim_absoluto += (p - GUIA_LARG if p > GUIA_LARG else 0) + GUIA_LARG

    # Centro geométrico da pista (para abaulamento)
    x_centro_pav = (x_pista_ini + x_pista_fim) / 2.0

    # ── 3. PONTOS DE DIVISÃO PARA COTAS DE COMPONENTES ────────────────────────
    pts_comp = [x_pista_ini]
    xc = x_pista_ini
    if dupla:
        xc += ai;      pts_comp.append(xc)
        xc += f;       pts_comp.append(xc)
        xc += f;       pts_comp.append(xc)
        xc += ae;      pts_comp.append(xc)
    else:
        xc += ae;      pts_comp.append(xc)
        xc += f;       pts_comp.append(xc)
        xc += f;       pts_comp.append(xc)
        xc += ae;      pts_comp.append(xc)

    # ── 4. FIGURA ─────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(14, 5), facecolor=COR_FUNDO)
    ax.set_facecolor(COR_FUNDO)

    # ── 5. FUNÇÕES AUXILIARES ─────────────────────────────────────────────────

    def _hachura_concreto(poligono_xy: list, angulo: float = 45.0,
                          espacamento: float = 12.0):
        """
        Gera hachura diagonal dentro de um polígono arbitrário.
        Método: cria linhas em toda a bbox e deixa a clip-region recortar.
        """
        from matplotlib.patches import Polygon as MPoly
        from matplotlib.path import Path
        import matplotlib.patheffects as pe

        poly_patch = MPoly(poligono_xy, closed=True,
                           facecolor='none', edgecolor='none', zorder=0)
        ax.add_patch(poly_patch)

        xs = [p[0] for p in poligono_xy]
        ys = [p[1] for p in poligono_xy]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)

        rad   = np.radians(angulo)
        slope = np.tan(rad)
        diag  = ((x_max - x_min)**2 + (y_max - y_min)**2) ** 0.5
        n     = int(diag * 2 / espacamento) + 2
        clip_path = Path(poligono_xy + [poligono_xy[0]])

        for k in range(-n, n):
            offset = k * espacamento
            x1 = x_min - diag
            y1 = slope * (x1 - x_min) + y_min + offset
            x2 = x_max + diag
            y2 = slope * (x2 - x_min) + y_min + offset
            line, = ax.plot([x1, x2], [y1, y2],
                            color=COR_HACH, lw=0.5, alpha=0.6, zorder=3)
            line.set_clip_path(clip_path, transform=ax.transData)

    def draw_nj(x_ini: float, espelhado: bool = False):
        """
        Desenha a barreira New Jersey com preenchimento e hachura.
        x_ini é a borda esquerda da barreira.
        Se espelhado=True, a geometria é refletida (NJ do lado direito).
        """
        pts_local = [
            (0,         0),
            (NJ_LARG,   0),
            (NJ_LARG,   NJ_DEGRAU_H),
            (NJ_CURVA_X1, NJ_CURVA_Y1),
            (NJ_TOPO_X, NJ_ALTO),
            (0,         NJ_ALTO),
        ]
        if espelhado:
            pts_local = [(NJ_LARG - px, py) for (px, py) in pts_local]

        pts_global = [(x_ini + px, py) for (px, py) in pts_local]

        ax.add_patch(Polygon(
            pts_global, closed=True,
            facecolor=COR_CONCRETO, edgecolor=COR_CONC_ED, lw=1.2, zorder=4
        ))
        _hachura_concreto(pts_global, angulo=45, espacamento=10)

    def draw_guia(x_ini: float, lado: str = 'e'):
        """Desenha guia de calçada (bloco retangular de concreto)."""
        x0 = x_ini if lado == 'e' else x_ini - GUIA_LARG
        pts = [(x0, 0), (x0 + GUIA_LARG, 0),
               (x0 + GUIA_LARG, GUIA_ALTO), (x0, GUIA_ALTO)]
        ax.add_patch(Polygon(
            pts, closed=True,
            facecolor=COR_CONCRETO, edgecolor=COR_CONC_ED, lw=1.2, zorder=4
        ))
        _hachura_concreto(pts, angulo=45, espacamento=10)

    def draw_cota_v(x: float, h_val: float, label_align: str = 'center'):
        """Cota vertical com seta bidirecional."""
        tick = 7
        ax.plot([x - tick, x + tick], [0, 0], color=COR_DIM, lw=0.8, zorder=5)
        ax.plot([x - tick, x + tick], [h_val, h_val], color=COR_DIM, lw=0.8, zorder=5)
        ax.annotate('', xy=(x, 0), xytext=(x, h_val),
                    arrowprops=dict(arrowstyle='<->', color=COR_DIM, lw=0.8),
                    zorder=5)

        txt = f"{h_val} cm"
        off = tick + 3
        ha_map = {'left': 'left', 'right': 'right', 'center': 'center'}
        ha  = ha_map.get(label_align, 'center')
        x_t = x + (off if label_align == 'left' else -off if label_align == 'right' else 0)
        ax.text(x_t, h_val + 4, txt, color=COR_TXT, ha=ha, va='bottom',
                fontsize=FS_COTA + 0.5, fontweight='bold', zorder=6,
                bbox=dict(boxstyle='round,pad=0.2', facecolor=COR_FUNDO,
                          edgecolor=COR_DIM, linewidth=0.4, alpha=0.88))

    def draw_cota_h(x_ini: float, x_fim: float, texto: str,
                    y_pos: float, cor: str = COR_DIM):
        """Cota horizontal com linhas de extensão e seta bidirecional."""
        tick = 6
        for xp in (x_ini, x_fim):
            ax.plot([xp, xp], [y_pos + tick, y_pos - tick],
                    color=cor, lw=0.7, zorder=5)
        ax.annotate('', xy=(x_ini, y_pos), xytext=(x_fim, y_pos),
                    arrowprops=dict(arrowstyle='<->', color=cor, lw=0.8),
                    zorder=5)
        ax.text((x_ini + x_fim) / 2, y_pos - tick - 3, texto,
                color=COR_TXT_DIM if cor == COR_DIM else COR_TXT,
                ha='center', va='top',
                fontsize=FS_COTA if cor == COR_DIM else FS_TOTAL,
                fontweight='normal' if cor == COR_DIM else 'bold',
                bbox=dict(boxstyle='round,pad=0.2', facecolor=COR_FUNDO,
                          edgecolor=cor, linewidth=0.5 if cor == COR_DIM else 0.8,
                          alpha=0.88))

    # ── 6. DESENHO DA SEÇÃO ───────────────────────────────────────────────────

    # Linha de base
    ax.plot([0.0, x_fim_absoluto], [0.0, 0.0], color=COR_LINHA, lw=1.5, zorder=1)

    # Pavimento asfáltico (perfil abaulado)
    n_pts = 80
    xs_pav = np.linspace(x_pista_ini, x_pista_fim, n_pts)
    # Perfil parabólico: h(x) = h_borda + (h_centro - h_borda) * [1 - ((x-centro)/(larg/2))^2]
    larg_pav = x_pista_fim - x_pista_ini
    ys_pav = h_borda + (h_centro - h_borda) * (
        1.0 - ((xs_pav - x_centro_pav) / (larg_pav / 2.0)) ** 2
    )
    # Fechamento do polígono de pavimento
    pav_x = [x_pista_ini] + list(xs_pav) + [x_pista_fim]
    pav_y = [0.0] + list(ys_pav) + [0.0]
    ax.add_patch(Polygon(
        list(zip(pav_x, pav_y)), closed=True,
        facecolor=COR_ASFALTO, edgecolor=COR_CONC_ED, lw=1.0, zorder=2
    ))
    # Linha de superfície do pavimento (mais visível)
    ax.plot(xs_pav, ys_pav, color=COR_CONC_ED, lw=1.0, zorder=3)

    # Barreiras New Jersey
    draw_nj(x_nj_esq_ini, espelhado=False)
    draw_nj(x_nj_dir_ini, espelhado=True)

    # Guias e passeios
    if p > 0:
        draw_guia(x_guia_esq_ini, lado='e')
        if not dupla:
            x_guia_dir_fim = x_fim_absoluto
            draw_guia(x_guia_dir_fim, lado='d')

    # ── 7. LINHA TRACEJADA COM DIVISÃO DOS COMPONENTES ────────────────────────
    y_linha_comp = max(h_borda, h_centro) + 18
    ax.plot([x_pista_ini, x_pista_fim], [y_linha_comp, y_linha_comp],
            color=COR_COMP, lw=0.8, linestyle='--', zorder=5)

    # Marcadores de divisão
    for xp in pts_comp[1:-1]:
        ax.plot([xp, xp], [y_linha_comp - 3, y_linha_comp + 3],
                color=COR_COMP, lw=0.8, zorder=5)

    # Rótulos de largura de cada componente
    if dupla:
        nomes  = [f"AI\n{ai}", f"F\n{f}", f"F\n{f}", f"AE\n{ae}"]
    else:
        nomes  = [f"AE\n{ae}", f"F\n{f}", f"F\n{f}", f"AE\n{ae}"]

    for i, nome in enumerate(nomes):
        x1, x2 = pts_comp[i], pts_comp[i + 1]
        ax.text((x1 + x2) / 2, y_linha_comp + 5, nome,
                color=COR_COMP, ha='center', va='bottom',
                fontsize=FS_COMP, fontweight='bold')

    # ── 8. COTAS VERTICAIS DE ESPESSURA ──────────────────────────────────────
    x_cota_esq = x_pista_ini + 14
    x_cota_cen = x_centro_pav
    x_cota_dir = x_pista_fim - 14

    draw_cota_v(x_cota_esq, h_borda,  label_align='left')
    draw_cota_v(x_cota_cen, h_centro, label_align='center')
    draw_cota_v(x_cota_dir, h_borda,  label_align='right')

    # ── 9. COTAS HORIZONTAIS INFERIORES ──────────────────────────────────────
    y_cota = -65.0

    pontos_cota = [0.0]
    if p > 0:
        pontos_cota.append(x_nj_esq_ini)
    pontos_cota += [x_nj_esq_fim, x_nj_dir_ini, x_nj_dir_fim]
    if p > 0 and not dupla:
        pontos_cota.append(x_fim_absoluto)

    rotulos_cota = []
    for i in range(len(pontos_cota) - 1):
        x1, x2 = pontos_cota[i], pontos_cota[i + 1]
        larg = x2 - x1
        if p > 0 and i == 0:
            rotulo = f"Passeio\n{larg:.0f}"
        elif (x1 == x_nj_esq_ini) or (x1 == x_nj_dir_ini):
            rotulo = f"NJ\n{larg:.0f}"
        elif (p > 0 and not dupla) and i == len(pontos_cota) - 2:
            rotulo = f"Passeio\n{larg:.0f}"
        else:
            rotulo = f"Pista\n{larg:.0f}"
        rotulos_cota.append(rotulo)

    for i, rotulo in enumerate(rotulos_cota):
        x1, x2 = pontos_cota[i], pontos_cota[i + 1]
        draw_cota_h(x1, x2, f"{x2-x1:.0f}", y_cota)

    # Cota total
    y_total = y_cota - 50.0
    draw_cota_h(0.0, x_fim_absoluto,
                f"Largura Total = {x_fim_absoluto:.0f} cm",
                y_total, cor=COR_GLOBAL)

    # ── 10. ENQUADRAMENTO ─────────────────────────────────────────────────────
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_xlim(-55.0, x_fim_absoluto + 55.0)
    ax.set_ylim(-195.0, NJ_ALTO + y_linha_comp + 30.0)
    plt.tight_layout(pad=0.4)

    return fig


# ============================================================================
# BLOCO DE TESTES
# ============================================================================

if __name__ == '__main__':
    import matplotlib
    matplotlib.use('TkAgg')

    # Pista Dupla – Classe I-A com passeio
    fig1 = desenhar_sec_transversal("I - A", h_borda=7, h_centro=12, passeio=200)
    plt.title("Seção Transversal – Classe I-A (pista dupla, c/ passeio)",
              color='white', fontsize=10)
    plt.show()

    # Pista Simples – Classe III sem passeio
    fig2 = desenhar_sec_transversal("III", h_borda=5, h_centro=10, passeio=False)
    plt.title("Seção Transversal – Classe III (pista simples, s/ passeio)",
              color='white', fontsize=10)
    plt.show()