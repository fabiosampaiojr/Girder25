# ============================================================================
# desenho_esquema_cargas.py  |  BridgeCalc – Módulo de Desenho Técnico
# ============================================================================
#
# Descrição : Gera o esquema técnico do modelo de carregamento NBR 7188
#             (carga móvel rodoviária – Trem-Tipo TB-450), exibindo:
#               • cargas distribuídas q1 (faixas laterais) e q2 (faixa central)
#               • cargas concentradas Q1 (eixos do veículo-tipo)
#             Inclui cotas, anotações de valores e indicador de escala visual.
#
# ─── CONTRATO DE INTERFACE (NÃO ALTERAR) ─────────────────────────────────────
#   Função  : desenhar_esquema_cargas(Q1, q1, q2) → matplotlib.figure.Figure
#   Tamanho : figsize=(5.81, 2.51), dpi=100  →  581 × 251 px
#   Uso     : integrado a QFrames fixos da interface gráfica do BridgeCalc.
# ─────────────────────────────────────────────────────────────────────────────
#
# Parâmetros de entrada:
#   Q1  – Carga concentrada por eixo     [kN]    float | None | 0 → omitido
#   q1  – Carga distribuída lateral      [kN/m]  float | None | 0 → omitido
#   q2  – Carga distribuída central      [kN/m]  float | None | 0 → omitido
#
# Comportamento para valores ausentes / nulos:
#   • None ou 0 → componente não desenhado; geometria e cotas preservadas.
#   • Valores negativos → tratados como 0.
#   • Tipos inválidos → tratados como 0 (sem exceção).
#
# Escala visual das cargas distribuídas:
#   • A carga de maior valor recebe H_SETA_MAX cm de altura de seta.
#   • As demais são proporcionais: h = H_SETA_MAX × (v / max_valor).
#   • Garantia de altura mínima H_SETA_MIN para cargas presentes.
#   • Um indicador de escala no canto superior direito exibe a referência.
#
# Precisão numérica: todos os valores são exibidos com 3 casas decimais.
#
# Versão    : 3.0
# ============================================================================

from __future__ import annotations

import matplotlib
matplotlib.use('Agg')

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches


# ─── PALETA DE CORES ─────────────────────────────────────────────────────────
# Tema escuro profissional, compatível com interfaces de engenharia.

COR_FUNDO      = "#252526"   # fundo da figura
COR_VIGA_FG    = "#3c3c3c"   # preenchimento do corpo da viga
COR_VIGA_ED    = "#c8c8c8"   # borda da viga
COR_VIGA_HI    = "#5a5a5a"   # faixa de realce superior da viga (efeito metálico)
COR_TXT        = "#f0f0f0"   # texto principal
COR_DIM        = "#888888"   # linhas de cota
COR_TXT_DIM    = "#b0b0b0"   # texto de cota
COR_Q1_DIST    = "#64B5F6"   # azul-médio – carga distribuída lateral (q1)
COR_Q2_DIST    = "#FFD54F"   # âmbar     – carga distribuída central (q2)
COR_Q_CONC     = "#EF9A9A"   # vermelho  – carga concentrada (Q1)
COR_TRACO      = "#555555"   # linhas tracejadas auxiliares
COR_LABEL_BG   = "#1e1e1e"   # fundo das etiquetas de valor
COR_ESCALA_REF = "#707070"   # indicador de escala


# ─── CONSTANTES DE GEOMETRIA  (coordenadas internas em centímetros) ───────────

VAO_COTA      = 150    # espaçamento entre eixos de carga concentrada [cm]
N_SEGMENTOS   = 4      # número de vãos entre eixos (= eixos exibidos − 1)
LARG_LATERAL  = 300    # largura de cada faixa lateral (q1) [cm]
VIGA_H        = 12     # espessura visual da viga [cm]

# Escala das setas de carga distribuída
H_SETA_MAX    = 70     # altura máxima (valor de referência) [cm]
H_SETA_MIN    = 20     # altura mínima garantida para carga > 0 [cm]

# Geometria vertical dos elementos
H_Q_CONC      = 112    # topo das setas de carga concentrada [cm]
Y_COTA_ESP    = -52    # y das cotas de espaçamento entre eixos [cm]
Y_COTA_TOT    = -92    # y da cota total do trem-tipo [cm]

# Tipografia
FS_COTA       = 6.5    # tamanho de fonte das cotas
FS_LABEL      = 6.5    # tamanho de fonte das etiquetas de carga
FS_ESCALA     = 5.8    # tamanho de fonte do indicador de escala

# Ordem de renderização (zorder)
Z_FILL        = 1      # polígonos de fundo
Z_TRACO       = 2      # linhas auxiliares tracejadas
Z_SETA_DIST   = 3      # setas de carga distribuída
Z_VIGA        = 4      # corpo da viga
Z_SETA_CONC   = 6      # setas de carga concentrada
Z_COTA        = 7      # linhas de cota
Z_LABEL       = 12     # etiquetas de valor (sempre na frente de tudo)


# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

def desenhar_esquema_cargas(Q1: float, q1: float, q2: float) -> plt.Figure:
    """
    Gera o esquema técnico de cargas conforme NBR 7188 (TB-450).

    Parâmetros
    ----------
    Q1 : float | None
        Carga concentrada por eixo [kN].
        None ou ≤ 0 → setas de Q1 não são desenhadas.
    q1 : float | None
        Carga distribuída nas faixas laterais [kN/m].
        None ou ≤ 0 → carga q1 não é desenhada.
    q2 : float | None
        Carga distribuída na faixa central [kN/m].
        None ou ≤ 0 → carga q2 não é desenhada.

    Retorna
    -------
    matplotlib.figure.Figure
        Figura 5.81 × 2.51 pol., 100 DPI → 581 × 251 px.
        Tamanho fixo; não alterar para compatibilidade com a UI.

    Notas
    -----
    - As alturas das setas de q1 e q2 são automaticamente escaladas de forma
      proporcional ao valor de cada carga, usando como referência o maior valor
      presente. Um indicador de escala é exibido no canto superior direito.
    - Todos os valores numéricos são formatados com 3 casas decimais.
    - Tipos inválidos e valores None são silenciosamente convertidos para 0.
    """

    # ── 0. NORMALIZAÇÃO E VALIDAÇÃO DE ENTRADAS ────────────────────────────────

    def _norm(v) -> float:
        """
        Converte qualquer entrada para float não-negativo.
        None, strings inválidas e tipos incompatíveis → 0.0 (sem exceção).
        """
        if v is None:
            return 0.0
        try:
            return max(0.0, float(v))
        except (TypeError, ValueError):
            return 0.0

    Q1v = _norm(Q1)
    q1v = _norm(q1)
    q2v = _norm(q2)

    tem_Q1 = Q1v > 0.0
    tem_q1 = q1v > 0.0
    tem_q2 = q2v > 0.0

    # ── 1. GEOMETRIA BASE ──────────────────────────────────────────────────────

    x_ini_central = LARG_LATERAL                          # início da faixa central
    x_fim_central = x_ini_central + N_SEGMENTOS * VAO_COTA  # fim da faixa central
    x_total       = x_fim_central + LARG_LATERAL           # largura total

    # Posições dos eixos de carga concentrada (internas ao trem-tipo)
    xs_eixos = [x_ini_central + i * VAO_COTA
                for i in range(1, N_SEGMENTOS)]            # ex.: [450, 600, 750]

    # ── 2. ESCALA PROPORCIONAL DAS CARGAS DISTRIBUÍDAS ────────────────────────
    # A carga de maior valor define H_SETA_MAX; as demais são proporcionais.

    cargas_presentes = [v for v in (q1v, q2v) if v > 0.0]
    ref_max = max(cargas_presentes) if cargas_presentes else 1.0

    def _h_seta(v: float) -> float:
        """Altura de seta proporcional ao valor; mínimo visual garantido."""
        if v <= 0.0:
            return 0.0
        return max(H_SETA_MIN, H_SETA_MAX * (v / ref_max))

    h_q1 = _h_seta(q1v)
    h_q2 = _h_seta(q2v)

    # ── 3. INICIALIZAÇÃO DA FIGURA ─────────────────────────────────────────────

    fig, ax = plt.subplots(figsize=(5.81, 2.51), dpi=100, facecolor=COR_FUNDO)
    ax.set_facecolor(COR_FUNDO)

    # ── 4. CLOSURES UTILITÁRIAS ────────────────────────────────────────────────

    def _label(x: float, y: float, texto: str,
               cor: str = COR_TXT, ha: str = 'center', va: str = 'bottom'):
        """
        Etiqueta de valor com caixa arredondada.
        Renderizada com Z_LABEL → sempre visível na frente de setas e polígonos.
        """
        ax.text(
            x, y, texto,
            color=cor, ha=ha, va=va,
            fontsize=FS_LABEL, fontweight='bold',
            zorder=Z_LABEL,
            bbox=dict(
                boxstyle='round,pad=0.28',
                facecolor=COR_LABEL_BG,
                edgecolor=cor,
                linewidth=0.70,
                alpha=0.96
            )
        )

    def _carga_distribuida(x_ini: float, x_fim: float, h: float,
                           valor: float, cor: str,
                           label_x_offset: float = 0.0):
        """
        Renderiza uma carga distribuída com:
          1. Polígono de preenchimento semitransparente (fundo).
          2. Linhas de borda lateral pontilhadas.
          3. Linha superior de distribuição.
          4. Setas verticais uniformemente espaçadas.
          5. Etiqueta de valor (Z_LABEL → sempre na frente das setas).

        Parâmetros
        ----------
        x_ini, x_fim      : extensão horizontal da carga [cm]
        h                 : altura das setas [cm]
        valor             : valor numérico para a etiqueta [kN/m]
        cor               : cor das setas e contornos
        label_x_offset    : deslocamento horizontal da etiqueta [cm]
        """
        if h <= 0.0:
            return

        # --- 1. Polígono de fundo semitransparente ---
        xs_fill = np.linspace(x_ini, x_fim, 60)
        ax.fill(
            [x_ini, *xs_fill, x_fim],
            [0.0,   *([h] * 60),  0.0],
            color=cor, alpha=0.10, zorder=Z_FILL
        )

        # --- 2. Bordas laterais pontilhadas ---
        for xb in (x_ini, x_fim):
            ax.plot([xb, xb], [0.0, h],
                    color=cor, lw=0.7, linestyle=':', alpha=0.50,
                    zorder=Z_FILL + 1)

        # --- 3. Linha superior de distribuição ---
        ax.plot([x_ini, x_fim], [h, h],
                color=cor, lw=1.5, zorder=Z_SETA_DIST)

        # --- 4. Setas verticais uniformemente espaçadas ---
        n_setas = max(4, int((x_fim - x_ini) / 14))
        for xs in np.linspace(x_ini, x_fim, n_setas):
            ax.annotate(
                '', xy=(xs, 0.0), xytext=(xs, h),
                arrowprops=dict(
                    arrowstyle='-|>',
                    color=cor,
                    lw=0.80,
                    mutation_scale=5.5
                ),
                zorder=Z_SETA_DIST
            )

        # --- 5. Etiqueta (na frente de tudo via Z_LABEL) ---
        lx = (x_ini + x_fim) / 2.0 + label_x_offset
        _label(lx, h + 5, f"{valor:.3f} kN/m", cor=cor)

    def _carga_concentrada(x: float, valor: float, show_label: bool):
        """
        Renderiza seta de carga concentrada.
        Etiqueta exibida apenas na seta indicada por show_label.
        """
        ax.annotate(
            '',
            xy=(x, VIGA_H / 2 + 1),
            xytext=(x, H_Q_CONC),
            arrowprops=dict(
                arrowstyle='-|>',
                color=COR_Q_CONC,
                lw=1.9,
                mutation_scale=13
            ),
            zorder=Z_SETA_CONC
        )
        if show_label:
            _label(x, H_Q_CONC + 5, f"{valor:.3f} kN", cor=COR_Q_CONC)

    def _cota_h(xa: float, xb: float, texto: str,
                y: float, cor: str = COR_DIM):
        """
        Cota horizontal bidirecional com:
          • Serifs verticais nas extremidades.
          • Seta dupla entre as extremidades.
          • Texto centralizado abaixo da linha de cota.
        """
        # Serifs
        for xp in (xa, xb):
            ax.plot([xp, xp], [y + 5, y - 5], color=cor, lw=0.75, zorder=Z_COTA)

        # Seta bidirecional (mutation_scale=1 → cabeças em pontos absolutos)
        ax.annotate(
            '', xy=(xa, y), xytext=(xb, y),
            arrowprops=dict(
                arrowstyle='<->, head_width=1.5, head_length=2.5',
                color=cor, lw=0.75, mutation_scale=1
            ),
            zorder=Z_COTA
        )

        # Texto
        ax.text(
            (xa + xb) / 2, y - 6, texto,
            color=COR_TXT_DIM, ha='center', va='top',
            fontsize=FS_COTA, zorder=Z_COTA + 1
        )

    # ── 5. VIGA ────────────────────────────────────────────────────────────────

    # Sombra sutil
    ax.add_patch(patches.Rectangle(
        (2, -VIGA_H / 2 - 2.5), x_total, VIGA_H,
        facecolor="#111111", edgecolor='none',
        alpha=0.55, zorder=Z_VIGA - 1
    ))

    # Corpo principal da viga
    ax.add_patch(patches.Rectangle(
        (0, -VIGA_H / 2), x_total, VIGA_H,
        facecolor=COR_VIGA_FG, edgecolor=COR_VIGA_ED,
        lw=1.4, zorder=Z_VIGA
    ))

    # Faixa de realce no topo (efeito metálico)
    ax.add_patch(patches.Rectangle(
        (1, VIGA_H / 2 - 3.0), x_total - 2, 3.0,
        facecolor=COR_VIGA_HI, edgecolor='none',
        alpha=0.65, zorder=Z_VIGA + 1
    ))

    # Delimitação das faixas (q1 | q2 | q1) – linhas verticais na viga
    for xd in (x_ini_central, x_fim_central):
        ax.plot([xd, xd], [-VIGA_H / 2, VIGA_H / 2],
                color=COR_VIGA_ED, lw=0.6, linestyle='--',
                alpha=0.45, zorder=Z_VIGA + 1)

    # ── 6. CARGAS DISTRIBUÍDAS q1 (FAIXAS LATERAIS) ───────────────────────────

    if tem_q1:
        _carga_distribuida(0, x_ini_central, h_q1, q1v, COR_Q1_DIST)
        _carga_distribuida(x_fim_central, x_total, h_q1, q1v, COR_Q1_DIST)

    # ── 7. CARGA DISTRIBUÍDA q2 (FAIXA CENTRAL) ───────────────────────────────

    if tem_q2:
        # Offset lateral da etiqueta para evitar sobreposição com a seta
        # central de Q1, que está exatamente no centro horizontal da zona q2.
        q2_offset = (VAO_COTA * 0.32) if tem_Q1 else 0.0
        _carga_distribuida(
            x_ini_central, x_fim_central,
            h_q2, q2v, COR_Q2_DIST,
            label_x_offset=q2_offset
        )

    # ── 8. CARGAS CONCENTRADAS Q1 ─────────────────────────────────────────────

    if tem_Q1:
        # Etiqueta exibida apenas na seta central do grupo
        idx_label = len(xs_eixos) // 2

        for i, xq in enumerate(xs_eixos):
            _carga_concentrada(xq, Q1v, show_label=(i == idx_label))

        # Linhas tracejadas de chamada (eixo → linha de cota)
        for xq in xs_eixos:
            ax.plot([xq, xq], [0.0, Y_COTA_ESP + 8],
                    color=COR_TRACO, lw=0.55,
                    linestyle='--', alpha=0.40, zorder=Z_TRACO)

    # ── 9. COTAS ───────────────────────────────────────────────────────────────

    # Cotas individuais de espaçamento entre eixos
    for i in range(N_SEGMENTOS):
        xa = x_ini_central + i * VAO_COTA
        _cota_h(xa, xa + VAO_COTA, f"{VAO_COTA} cm", Y_COTA_ESP)

    # Cota total do trem-tipo
    _cota_h(
        x_ini_central, x_fim_central,
        f"Trem-Tipo = {N_SEGMENTOS * VAO_COTA} cm",
        Y_COTA_TOT, cor=COR_Q_CONC
    )

    # ── 10. INDICADOR DE ESCALA DAS CARGAS DISTRIBUÍDAS ───────────────────────
    # Exibido apenas quando há ao menos uma carga distribuída presente.
    # Localização: margem direita, alinhado à altura de H_SETA_MAX.

    if cargas_presentes:
        # Coordenadas do indicador (à direita da viga, margem direita)
        xi_esc  = x_total + 28
        y_base  = 0.0
        y_topo  = H_SETA_MAX

        # Linha vertical de referência
        ax.plot([xi_esc, xi_esc], [y_base, y_topo],
                color=COR_ESCALA_REF, lw=1.0, alpha=0.80, zorder=Z_COTA)

        # Ticks horizontais
        for yt in (y_base, y_topo):
            ax.plot([xi_esc - 5, xi_esc + 5], [yt, yt],
                    color=COR_ESCALA_REF, lw=0.85, alpha=0.80, zorder=Z_COTA)

        # Texto de referência
        ax.text(
            xi_esc + 7,
            (y_base + y_topo) / 2,
            f"= {ref_max:.3f}\nkN/m",
            color=COR_TXT_DIM, ha='left', va='center',
            fontsize=FS_ESCALA, alpha=0.90,
            zorder=Z_COTA + 1
        )

    # ── 11. AJUSTES FINAIS ─────────────────────────────────────────────────────

    ax.axis('off')
    ax.set_xlim(-62, x_total + 95)     # margem esquerda + espaço para indicador
    ax.set_ylim(-120, H_Q_CONC + 55)   # margem inferior + topo com label Q1
    plt.tight_layout(pad=0.35)

    return fig


# ============================================================================
# BLOCO DE TESTES  (executado apenas com  python desenho_esquema_cargas.py)
# ============================================================================

if __name__ == '__main__':
    import matplotlib as mpl
    mpl.use('TkAgg')

    _casos = [
        # (Q1,     q1,    q2,    título)
        (450.0,  5.000, 3.000,  "Caso padrão NBR 7188"),
        (450.0,  15.0,  3.500,  "Escala proporcional q1 >> q2"),
        (450.0,  5.000, 5.000,  "q1 = q2 (setas iguais)"),
        (None,   5.000, 3.000,  "Sem Q1 (Q1 = None)"),
        (450.0,  None,  3.000,  "Sem q1 (q1 = None)"),
        (450.0,  5.000, None,   "Sem q2 (q2 = None)"),
        (450.0,  None,  None,   "Apenas Q1"),
        (None,   5.000, None,   "Apenas q1"),
        (None,   None,  3.000,  "Apenas q2"),
        (0,      0,     0,      "Todos nulos → apenas viga e cotas"),
    ]

    for Q1_, q1_, q2_, titulo in _casos:
        fig = desenhar_esquema_cargas(Q1_, q1_, q2_)
        fig.suptitle(titulo, color='#cccccc', fontsize=8, y=0.97)

    plt.show()
