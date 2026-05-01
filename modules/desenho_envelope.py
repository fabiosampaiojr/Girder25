# ============================================================================
# DESENHO_ENVELOPE.PY  –  v2.1
# ============================================================================
#
# Módulo de plotagem da envoltória final de cálculo de esforços.
#
# Fornece duas funções públicas:
#
#   desenhar_envelope_calculo(esforcos_calculo, esforco, combinacao,
#                             fig_anterior=None) → Figure
#       Gera a figura matplotlib da envoltória de cortante ou momento para
#       o estado limite (ELU / ELS) especificado.
#
#   ativar_interatividade_envelope(fig, canvas) → None
#       Ativa hover com tooltip, zoom via scroll e reset via duplo-clique
#       para uma figura gerada por desenhar_envelope_calculo().  Deve ser
#       chamada depois que o canvas Qt foi criado e adicionado ao layout.
#
# Características visuais
# ------------------------
#   - Tema escuro técnico, compatível com o padrão visual do software.
#   - Preenchimento verde (#81c784) entre zero e a curva de máximos.
#   - Preenchimento vermelho (#e57373) entre zero e a curva de mínimos.
#   - Linhas de máximo (sólida) e mínimo (tracejada).
#   - Anotação dos extremos globais com seta e caixa de texto.
#   - Tamanho nominal: 911 × 461 px @ 100 DPI (adaptável pelo canvas Qt).
#
# [v2.1] CORREÇÃO: Adicionado parâmetro `fig_anterior` para fechar figura
#         anterior, evitando acúmulo de figuras abertas (RuntimeWarning).
# ============================================================================

from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

# ----------------------------------------------------------------------------
# Constantes de estilo (dark theme, compatível com o padrão do software)
# ----------------------------------------------------------------------------
_COR_FUNDO_FIG = '#2b2b2b'
_COR_FUNDO_AX  = '#1e1e1e'
_COR_GRADE     = '#3a3a3a'
_COR_SPINE     = '#555555'
_COR_TICK      = '#b0b0b0'
_COR_ZERO      = '#607d8b'

_COR_MAX_FILL  = '#81c784'   # Verde claro — preenchimento dos máximos
_COR_MAX_LINE  = '#a5d6a7'   # Verde mais claro — linha de máximos
_COR_MIN_FILL  = '#e57373'   # Vermelho claro — preenchimento dos mínimos
_COR_MIN_LINE  = '#ef9a9a'   # Vermelho mais claro — linha de mínimos

_COR_EXT_MAX   = '#A5D6A7'   # Verde — anotação do extremo máximo
_COR_EXT_MIN   = '#EF9A9A'   # Vermelho — anotação do extremo mínimo


# ============================================================================
# API pública
# ============================================================================

def desenhar_envelope_calculo(
    esforcos_calculo,   # objeto EsforcosCalculo (do Gerenciador_Dados)
    esforco: str,       # "cortante" ou "momento"
    combinacao: str,    # "ELU" ou "ELS"
    fig_anterior: Optional[Figure] = None,   # ← [v2.1] Parâmetro adicionado
) -> Figure:
    """
    Gera a figura da envoltória de esforços para o estado limite escolhido.

    Parameters
    ----------
    esforcos_calculo : EsforcosCalculo
        Objeto contendo os resultados das combinações (ELU e ELS), normalmente
        obtido via DataManager.get_esforcos_calculo().  Deve possuir o atributo
        ``resultados`` com estrutura::

            {
              "ELU": {"Cortante": [[cabeçalho], [linha], ...],
                      "Momento":  [[cabeçalho], [linha], ...]},
              "ELS": { ... }
            }

        Cada linha de dados segue o formato: [posicao, nome_secao, max, min].

    esforco : str
        Tipo de esforço a ser plotado.  Aceita ``"cortante"`` ou ``"momento"``
        (insensível a maiúsculas/minúsculas).

    combinacao : str
        Estado limite da envoltória.  Aceita ``"ELU"`` ou ``"ELS"``
        (insensível a maiúsculas/minúsculas).

    fig_anterior : matplotlib.figure.Figure, optional
        [v2.1] Se fornecida, essa figura será fechada com ``plt.close()``
        antes da criação da nova.  Isso evita o acúmulo de figuras abertas
        em chamadas sucessivas da função.

    Returns
    -------
    matplotlib.figure.Figure
        Figura pronta para exibição ou exportação.

    Notes
    -----
    Para ativar interatividade (hover, zoom, reset), chame em seguida::

        canvas = FigureCanvasQTAgg(fig)
        ativar_interatividade_envelope(fig, canvas)

    Raises
    ------
    ValueError
        Se ``esforco`` ou ``combinacao`` forem inválidos.
    AttributeError
        Se o objeto não possuir o atributo ``resultados``.
    KeyError
        Se o estado ou tipo não forem encontrados nos resultados.
    """
    # [v2.1] Fecha a figura anterior, se fornecida, para liberar memória
    if fig_anterior is not None:
        plt.close(fig_anterior)

    esf_lower  = esforco.lower()
    comb_upper = combinacao.upper()

    if esf_lower not in ("cortante", "momento"):
        raise ValueError("Parâmetro 'esforco' deve ser 'cortante' ou 'momento'.")
    if comb_upper not in ("ELU", "ELS"):
        raise ValueError("Parâmetro 'combinacao' deve ser 'ELU' ou 'ELS'.")

    tipo   = {"cortante": "Cortante", "momento": "Momento"}[esf_lower]
    estado = comb_upper

    if not hasattr(esforcos_calculo, 'resultados'):
        raise AttributeError("O objeto fornecido não possui o atributo 'resultados'.")
    resultados = esforcos_calculo.resultados

    if estado not in resultados:
        raise KeyError(f"Estado '{estado}' não encontrado nos resultados.")
    if tipo not in resultados[estado]:
        raise KeyError(
            f"Tipo '{tipo}' não encontrado nos resultados para o estado '{estado}'.")

    tabela = resultados[estado][tipo]   # [[cabeçalho], [linha], ...]
    dados  = _extrair_dados_tabela(tabela)

    return _plotar_envelope(
        estado=estado,
        tipo=tipo,
        posicoes=dados['posicoes'],
        maxs=dados['maxs'],
        mins=dados['mins'],
        labels=dados['labels'],
        unidade="kN·m" if tipo == "Momento" else "kN",
        simbolo="M"    if tipo == "Momento" else "V",
    )


def ativar_interatividade_envelope(fig: Figure, canvas) -> None:
    """
    Ativa interatividade (hover, scroll zoom, duplo-clique reset) para uma
    figura gerada por :func:`desenhar_envelope_calculo`.

    Esta função deve ser chamada **após** a figura ter sido associada a um
    canvas interativo (``FigureCanvasQTAgg``) e o canvas ter sido adicionado
    ao layout da janela.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        Figura retornada por ``desenhar_envelope_calculo``, contendo o
        atributo interno ``_envoltoria_data``.
    canvas : FigureCanvasQTAgg (ou compatível)
        Canvas Qt onde a figura está renderizada.

    Notes
    -----
    Comportamentos ativados:

    * **Hover** — linha vertical laranja, pontos destacados e tooltip com
      os valores exatos de Msd,max e Msd,min na seção mais próxima do cursor.
    * **Scroll** — zoom no eixo Y centrado na posição do cursor.
    * **Duplo-clique** — restaura os limites originais do eixo Y.
    """
    data = getattr(fig, '_envoltoria_data', None)
    if data is None:
        return

    ax      = data['ax']
    xs      = data['xs']
    mxs     = data['mxs']
    mns     = data['mns']
    labels  = data['labels']
    unidade = data['unidade']
    simbolo = data['simbolo']

    # Captura os limites originais para o reset por duplo-clique
    y_lo_orig, y_hi_orig = ax.get_ylim()

    # ── Elementos visuais do hover ────────────────────────────────────────────
    vline, = ax.plot([], [], color='#FFA726', lw=0.9,
                     linestyle='--', alpha=0.0, zorder=8)
    dot_max = ax.scatter([], [], s=50, color=_COR_EXT_MAX,
                         zorder=9, alpha=0.0, edgecolors='none')
    dot_min = ax.scatter([], [], s=50, color=_COR_EXT_MIN,
                         zorder=9, alpha=0.0, edgecolors='none')
    tooltip = ax.text(
        0.018, 0.975, '',
        transform=ax.transAxes,
        fontsize=8.0, color='white',
        va='top', ha='left',
        linespacing=1.65,
        bbox=dict(
            boxstyle='round,pad=0.50',
            facecolor='#0d0d1a',
            edgecolor='#90CAF9',
            linewidth=0.9,
            alpha=0.0,
        ),
        zorder=20,
        visible=False,
    )

    def _mais_proximo(x_cursor: float) -> int:
        """Retorna o índice da seção mais próxima do cursor."""
        return int(np.argmin(np.abs(xs - x_cursor)))

    # ── Callbacks de evento ───────────────────────────────────────────────────

    def on_move(event):
        if event.inaxes is not ax or event.xdata is None:
            vline.set_alpha(0.0)
            dot_max.set_alpha(0.0)
            dot_min.set_alpha(0.0)
            tooltip.set_visible(False)
            canvas.draw_idle()
            return

        idx    = _mais_proximo(event.xdata)
        x_sec  = float(xs[idx])
        mx     = float(mxs[idx])
        mn     = float(mns[idx])

        y_lo_cur, y_hi_cur = ax.get_ylim()
        vline.set_data([x_sec, x_sec], [y_lo_cur, y_hi_cur])
        vline.set_alpha(0.55)

        dot_max.set_offsets([[x_sec, mx]])
        dot_max.set_alpha(0.90)
        dot_min.set_offsets([[x_sec, mn]])
        dot_min.set_alpha(0.90)

        txt = (f"  {labels[idx]}    ·    x = {x_sec:.2f} m\n"
               f"  {simbolo}sd,max = {mx:+.3f}  {unidade}\n"
               f"  {simbolo}sd,min = {mn:+.3f}  {unidade}")
        tooltip.set_text(txt)
        tooltip.get_bbox_patch().set_alpha(0.93)
        tooltip.set_visible(True)
        canvas.draw_idle()

    def on_scroll(event):
        if event.inaxes is not ax:
            return
        y_lo_cur, y_hi_cur = ax.get_ylim()
        y_c   = (float(event.ydata) if event.ydata is not None
                 else (y_lo_cur + y_hi_cur) / 2.0)
        fator = 0.85 if event.button == 'up' else (1.0 / 0.85)
        ax.set_ylim(y_c - (y_c - y_lo_cur) * fator,
                    y_c + (y_hi_cur - y_c) * fator)
        canvas.draw_idle()

    def on_click(event):
        if event.inaxes is ax and event.dblclick:
            ax.set_ylim(y_lo_orig, y_hi_orig)
            canvas.draw_idle()

    canvas.mpl_connect('motion_notify_event', on_move)
    canvas.mpl_connect('scroll_event',        on_scroll)
    canvas.mpl_connect('button_press_event',  on_click)


# ============================================================================
# Funções privadas auxiliares
# ============================================================================

def _extrair_dados_tabela(tabela: List[List]) -> Dict:
    """
    Converte a tabela de envoltória (formato do Calculadora_Esforcos) em
    dicionário com arrays de posições, máximos, mínimos e rótulos de seção.

    Parameters
    ----------
    tabela : list of list
        Primeira lista é o cabeçalho; as seguintes são linhas de dados com
        formato ``[posicao, nome_secao, val_max, val_min]``.

    Returns
    -------
    dict
        Chaves: ``'posicoes'``, ``'maxs'``, ``'mins'``, ``'labels'``.

    Raises
    ------
    ValueError
        Se a tabela estiver vazia ou com formato inválido.
    """
    if len(tabela) < 2:
        raise ValueError("Tabela de envoltória vazia ou sem dados.")
    if len(tabela[0]) < 4:
        raise ValueError("Formato inesperado da tabela de envoltória "
                         f"(esperado ≥ 4 colunas, recebido {len(tabela[0])}).")

    posicoes, maxs, mins, labels = [], [], [], []

    for linha in tabela[1:]:
        if len(linha) < 4:
            continue
        # Nova estrutura: col 0 = Posição [m] (float), col 1 = rótulo da seção (str)
        posicoes.append(float(linha[0]))
        labels.append(str(linha[1]))
        maxs.append(float(linha[2]))
        mins.append(float(linha[3]))

    return {
        'posicoes': np.array(posicoes, dtype=float),
        'maxs':     np.array(maxs,     dtype=float),
        'mins':     np.array(mins,     dtype=float),
        'labels':   labels,
    }


def _plotar_envelope(
    estado: str,
    tipo: str,
    posicoes: np.ndarray,
    maxs: np.ndarray,
    mins: np.ndarray,
    labels: List[str],
    unidade: str,
    simbolo: str,
) -> Figure:
    """
    Gera a figura matplotlib com a envoltória no estilo técnico dark do software.

    Parameters
    ----------
    estado : str
        "ELU" ou "ELS" — usado no título.
    tipo : str
        "Cortante" ou "Momento" — determina inversão do eixo Y e legenda.
    posicoes, maxs, mins : numpy.ndarray
        Arrays 1-D de mesma dimensão com posições (m) e valores dos esforços.
    labels : list of str
        Nomes das seções, usados nas anotações de extremos.
    unidade : str
        Unidade para os rótulos dos eixos (ex.: "kN·m" ou "kN").
    simbolo : str
        Símbolo do esforço (ex.: "M" ou "V").

    Returns
    -------
    matplotlib.figure.Figure
        Figura com ``_envoltoria_data`` definido para uso posterior em
        :func:`ativar_interatividade_envelope`.
    """
    # Convenção de pontes: momento positivo → tração nas fibras inferiores
    inverter_y = (tipo == "Momento")

    fig, ax = plt.subplots(figsize=(9.11, 4.61), dpi=100)

    # ── Estilo escuro ─────────────────────────────────────────────────────────
    fig.patch.set_facecolor(_COR_FUNDO_FIG)
    ax.set_facecolor(_COR_FUNDO_AX)
    for spine in ax.spines.values():
        spine.set_color(_COR_SPINE)
        spine.set_linewidth(0.8)
    ax.tick_params(colors=_COR_TICK, labelsize=8.5, length=4, width=0.7)
    ax.xaxis.label.set_color(_COR_TICK)
    ax.yaxis.label.set_color(_COR_TICK)

    # ── Dados ausentes ────────────────────────────────────────────────────────
    if len(posicoes) == 0:
        ax.text(0.5, 0.5, "Sem dados disponíveis para esta envoltória.",
                color='white', ha='center', va='center',
                transform=ax.transAxes, fontsize=11)
        plt.subplots_adjust(left=0.09, right=0.97, top=0.87, bottom=0.10)
        return fig

    # ── Grade técnica ─────────────────────────────────────────────────────────
    ax.yaxis.grid(True, color=_COR_GRADE, linewidth=0.5,
                  linestyle='--', alpha=0.7, zorder=1)
    for xp in posicoes:
        ax.axvline(xp, color=_COR_GRADE, linewidth=0.35,
                   linestyle=':', alpha=0.45, zorder=1)
    ax.set_axisbelow(True)

    # ── Linha de referência zero ──────────────────────────────────────────────
    ax.axhline(0.0, color=_COR_ZERO, linewidth=1.2,
               linestyle='-', alpha=0.9, zorder=4)

    # ── Preenchimentos ────────────────────────────────────────────────────────
    ax.fill_between(posicoes, maxs, 0, where=(maxs >= 0),
                    facecolor=_COR_MAX_FILL, alpha=0.50, linewidth=0, zorder=2)
    ax.fill_between(posicoes, mins, 0, where=(mins <= 0),
                    facecolor=_COR_MIN_FILL, alpha=0.40, linewidth=0, zorder=2)

    # ── Linhas de envoltória ──────────────────────────────────────────────────
    ax.plot(posicoes, maxs, color=_COR_MAX_LINE, linewidth=2.2,
            solid_capstyle='round', zorder=6,
            label=f'{simbolo}$_{{sd,max}}$')
    ax.plot(posicoes, mins, color=_COR_MIN_LINE, linewidth=2.0,
            linestyle='--', dash_capstyle='round', zorder=6,
            label=f'{simbolo}$_{{sd,min}}$')

    # ── Marcadores de seção no eixo x ─────────────────────────────────────────
    _marcar_secoes(ax, posicoes, labels)

    # ── Anotações dos extremos globais ────────────────────────────────────────
    idx_max = int(np.argmax(maxs))
    idx_min = int(np.argmin(mins))
    _anotar_extremo(
        ax, posicoes, maxs, mins, idx_max,
        f"Máx: {maxs[idx_max]:+.2f} {unidade}\n{labels[idx_max]}",
        _COR_EXT_MAX, acima=True,  inverter=inverter_y,
    )
    _anotar_extremo(
        ax, posicoes, maxs, mins, idx_min,
        f"Mín: {mins[idx_min]:+.2f} {unidade}\n{labels[idx_min]}",
        _COR_EXT_MIN, acima=False, inverter=inverter_y,
    )

    # ── Limites dos eixos ─────────────────────────────────────────────────────
    margem_x = 0.03 * (posicoes[-1] - posicoes[0]) if len(posicoes) > 1 else 0.5
    ax.set_xlim(posicoes[0] - margem_x, posicoes[-1] + margem_x)

    y_lo  = min(mins.min(), 0.0)
    y_hi  = max(maxs.max(), 0.0)
    span  = (y_hi - y_lo) if y_hi != y_lo else max(abs(y_hi), 1.0)
    ax.set_ylim(y_lo - 0.22 * span, y_hi + 0.22 * span)

    ax.set_xlabel("Posição  [m]", fontsize=10, labelpad=6)
    ax.set_ylabel(f"{simbolo}$_{{sd}}$  [{unidade}]", fontsize=10, labelpad=6)

    if inverter_y:
        ax.invert_yaxis()
        ax.text(0.01, 0.02,
                "↓  M⁺ → tração nas fibras inferiores  (conv. pontes)",
                transform=ax.transAxes,
                color=_COR_TICK, fontsize=7, alpha=0.65,
                ha='left', va='bottom')

    # ── Legenda ───────────────────────────────────────────────────────────────
    legenda = ax.legend(
        handles=[
            Line2D([0], [0], color=_COR_MAX_LINE, linewidth=2.0,
                   label=f'{simbolo}$_{{sd,max}}$'),
            Line2D([0], [0], color=_COR_MIN_LINE, linewidth=2.0,
                   linestyle='--', label=f'{simbolo}$_{{sd,min}}$'),
        ],
        fontsize=8.0,
        loc='upper right',
        framealpha=0.92,
        edgecolor=_COR_SPINE,
        handlelength=1.8,
        borderpad=0.8,
    )
    legenda.get_frame().set_facecolor(_COR_FUNDO_FIG)
    for txt in legenda.get_texts():
        txt.set_color(_COR_TICK)

    # ── Títulos ───────────────────────────────────────────────────────────────
    _montar_titulos(fig, estado, tipo)

    # ── Dados para interatividade (armazenados na figura) ─────────────────────
    fig._envoltoria_data = {          # type: ignore[attr-defined]
        'ax':       ax,
        'xs':       posicoes,
        'mxs':      maxs,
        'mns':      mins,
        'labels':   labels,
        'unidade':  unidade,
        'simbolo':  simbolo,
        'inverter_y': inverter_y,
    }

    plt.subplots_adjust(left=0.09, right=0.97, top=0.87, bottom=0.10)
    return fig


# ============================================================================
# Funções auxiliares de desenho
# ============================================================================

def _marcar_secoes(ax, xs: np.ndarray, labels: List[str]) -> None:
    """
    Define os ticks do eixo x nas posições das seções, com espaçamento mínimo
    para evitar sobreposição de rótulos.
    """
    if len(xs) == 0:
        return
    n        = len(xs)
    span     = xs[-1] - xs[0] if xs[-1] != xs[0] else 1.0
    min_dist = span * 0.08

    ticks_x  = []
    ultimo_x = -math.inf
    for i, x in enumerate(xs):
        if i == 0 or i == n - 1 or (x - ultimo_x) >= min_dist:
            ticks_x.append(x)
            ultimo_x = x

    ax.set_xticks(ticks_x)
    ax.set_xticklabels([f"{x:.2f}" for x in ticks_x],
                       fontsize=8.0, color=_COR_TICK)


def _anotar_extremo(
    ax,
    xs: np.ndarray,
    mxs: np.ndarray,
    mns: np.ndarray,
    idx: int,
    texto: str,
    cor: str,
    acima: bool,
    inverter: bool,
) -> None:
    """
    Adiciona um marcador circular e uma anotação com seta no ponto extremo
    especificado pelo índice ``idx``.
    """
    x_val = xs[idx]
    y_val = mxs[idx] if acima else mns[idx]

    ax.scatter([x_val], [y_val], s=60, color=cor, zorder=9,
               edgecolors='none', alpha=0.95)

    y_lo      = min(mns.min(), 0.0)
    y_hi      = max(mxs.max(), 0.0)
    span      = (y_hi - y_lo) if y_hi != y_lo else max(abs(y_hi), 1.0)
    offset    = 0.12 * span

    sobe_no_plot = acima != inverter
    y_text       = y_val + (offset if sobe_no_plot else -offset)
    va_text      = 'bottom' if sobe_no_plot else 'top'

    ax.annotate(
        texto,
        xy=(x_val, y_val),
        xytext=(x_val, y_text),
        fontsize=8.0, fontweight='bold', color=cor,
        ha='center', va=va_text,
        arrowprops=dict(
            arrowstyle='-|>',
            color=cor, lw=0.9,
            mutation_scale=10,
            connectionstyle='arc3,rad=0.0',
        ),
        bbox=dict(
            boxstyle='round,pad=0.35',
            facecolor=_COR_FUNDO_FIG,
            edgecolor=cor,
            linewidth=0.8,
            alpha=0.92,
        ),
        zorder=10,
    )


def _montar_titulos(fig: Figure, estado: str, tipo: str) -> None:
    """Insere título principal e subtítulo com informações do estado limite."""
    combinacao_str = "Normal" if estado == "ELU" else "Frequente"
    titulo    = (f"Envoltória de {tipo}  ·  {estado}  "
                 f"(Combinação {combinacao_str})")
    subtitulo = "Coeficientes conforme definidos pelo usuário"

    fig.text(0.50, 0.960, titulo,
             ha='center', va='top',
             fontsize=10.5, fontweight='bold', color='white')
    fig.text(0.50, 0.910, subtitulo,
             ha='center', va='top',
             fontsize=8.0, color=_COR_TICK, alpha=0.85)


# ============================================================================
# Bloco de testes (executado apenas quando o módulo é rodado diretamente)
# ============================================================================
if __name__ == "__main__":
    """
    Testes de integração com dados sintéticos.

    Gera PNGs de todas as combinações (ELU/ELS × Cortante/Momento) e,
    se PyQt6 estiver disponível, abre uma janela interativa de demonstração.
    """
    import matplotlib
    matplotlib.use('QtAgg')   # deve ser definido antes do primeiro import de pyplot

    print("=" * 70)
    print("TESTES DO MÓDULO DESENHO_ENVELOPE")
    print("=" * 70)

    # ── Mock do objeto EsforcosCalculo ────────────────────────────────────────
    class _EsforcosCalculoMock:
        def __init__(self, resultados):
            self.resultados = resultados

    L         = 12.0
    n_secoes  = 13
    xs_mock   = np.linspace(0, L, n_secoes)

    def _gerar_tabela(tipo: str, fator: float = 1.0) -> List[List]:
        cab    = ["Seção", "Posição [m]",
                  f"{'M' if tipo == 'Momento' else 'V'}sd_max",
                  f"{'M' if tipo == 'Momento' else 'V'}sd_min"]
        linhas = [cab]
        for i, x in enumerate(xs_mock):
            if tipo == "Momento":
                val_max = fator * 150 * (x / L) * (1 - x / L) * 4
                val_min = -fator * 30  * (x / L) * (1 - x / L) * 4
            else:
                val_max =  fator * 100 * (1 - x / L)
                val_min = -fator * 100 * (x / L)
            linhas.append([f"S{i + 1}", round(x, 4),
                           round(val_max, 4), round(val_min, 4)])
        return linhas

    mock_resultados = {
        "ELU": {
            "Cortante": _gerar_tabela("Cortante", 1.0),
            "Momento":  _gerar_tabela("Momento",  1.0),
        },
        "ELS": {
            "Cortante": _gerar_tabela("Cortante", 0.7),
            "Momento":  _gerar_tabela("Momento",  0.7),
        },
    }
    esf_mock = _EsforcosCalculoMock(mock_resultados)

    # ── Geração de PNGs ───────────────────────────────────────────────────────
    casos = [
        ("momento",  "ELU", "teste_envelope_momento_ELU.png"),
        ("momento",  "ELS", "teste_envelope_momento_ELS.png"),
        ("cortante", "ELU", "teste_envelope_cortante_ELU.png"),
        ("cortante", "ELS", "teste_envelope_cortante_ELS.png"),
    ]
    for esf, comb, nome_arq in casos:
        print(f"\n>> Gerando figura: {esf.upper()} – {comb}")
        # [v2.1] Durante testes também passamos None, mas poderíamos fechar manualmente
        fig = desenhar_envelope_calculo(esf_mock, esf, comb)
        fig.savefig(nome_arq, dpi=100, facecolor=_COR_FUNDO_FIG)
        print(f"   Salvo: {nome_arq}")
        plt.close(fig)   # Fecha a figura após salvar (boa prática em testes)

    # ── Verificação de tratamento de erros ────────────────────────────────────
    print("\n>> Verificação de tratamento de erros")
    for esf, comb in [("invalido", "ELU"), ("momento", "XYZ")]:
        try:
            desenhar_envelope_calculo(esf_mock, esf, comb)
        except ValueError as e:
            print(f"   ValueError capturado (esperado): {e}")

    # ── Janela interativa (opcional, requer PyQt6) ────────────────────────────
    print("\n>> Janela interativa (requer PyQt6)")
    try:
        import sys
        from PyQt6.QtWidgets import (
            QApplication, QMainWindow, QVBoxLayout, QWidget)
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as _Canvas

        app = QApplication.instance() or QApplication(sys.argv)

        class _TestWindow(QMainWindow):
            def __init__(self, fig: Figure):
                super().__init__()
                self.setWindowTitle("Teste Interativo — Envoltória de Momento (ELU)")
                self.setGeometry(100, 100, 911, 461)
                central = QWidget()
                self.setCentralWidget(central)
                layout = QVBoxLayout(central)
                layout.setContentsMargins(0, 0, 0, 0)
                self.canvas = _Canvas(fig)
                layout.addWidget(self.canvas)
                ativar_interatividade_envelope(fig, self.canvas)

        fig_interativa = desenhar_envelope_calculo(esf_mock, "momento", "ELU")
        window = _TestWindow(fig_interativa)
        window.show()
        print("   Janela aberta. Feche-a para encerrar.")
        app.exec()

    except ImportError:
        print("   PyQt6 não encontrado. Teste interativo ignorado.")
    except Exception as exc:
        print(f"   Erro ao criar janela interativa: {exc}")

    print("\n✅ Todos os testes concluídos.")