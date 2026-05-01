# =============================================================================
# exportar_dxf.py  |  BridgeCalc – Exportador DXF Profissional
# =============================================================================
# Versão  : 3.0
# Descrição: Exportação técnica nível CAD de figuras Matplotlib para DXF.
#
# Melhorias v3.0 (em relação à v2.x):
#   [FIX-1] FancyBboxPatch (vigas) e Polygon (apoios, seções, estribos)
#           não eram detectados. Substituídos por handler genérico via path.
#   [FIX-2] FancyArrowPatch (setas de cota e carga) nunca aparecia em
#           ax.get_children(). Agora extraído via Annotation.arrow_patch.
#   [FIX-3] Cor reduzida incorretamente a apenas branco/preto. Substituída
#           por True Color RGB (24 bits), suportado desde DXF R2010.
#   [FIX-4] PolyCollection / PathCollection / LineCollection (fill_between,
#           fill, hachuras) não eram processados. Adicionado handler dedicado.
#   [FIX-5] Sistema de coordenadas inconsistente para figuras multi-eixo
#           (ex.: detalhamento_armadura com ax_panel em transAxes).
#           Resolução: pipeline unificado display→DXF via fig.canvas.draw().
#   [FIX-6] Estilos de linha (dashed, dotted, dashdot) não eram mapeados.
#           Agora mapeados para linetypes DXF padrão ISO.
#   [FIX-7] Erros em artistas individuais não interrompem a exportação.
#
# Artistas suportados:
#   · Patch (genérico)  – FancyBboxPatch, Polygon, Rectangle, PathPatch, ...
#   · Circle            – rótulas, roletes, armaduras (entidade CIRCLE exata)
#   · Line2D            – linhas, hachuras, eixos, cotas
#   · Annotation        – setas de cotas e cargas (texto + FancyArrowPatch)
#   · FancyArrowPatch   – setas autônomas
#   · PolyCollection    – fill_between, fill (preenchimentos)
#   · PathCollection    – coleções de caminhos
#   · LineCollection    – coleções de linhas
#   · Text / MText      – etiquetas e anotações
#
# Organização de camadas:
#   Cada combinação (tipo_de_artista, cor_RGB) gera uma camada própria:
#   ex.: "LINHA_FF9800" (laranja), "FILL_90CAF9" (azul claro), ...
#   Permite filtrar/congelar elementos por tipo ou cor no CAD.
# =============================================================================

from __future__ import annotations

import numpy as np
import matplotlib
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.lines
import matplotlib.text
import matplotlib.collections


# ─── MAPEAMENTO: espessura de linha Matplotlib (pt) → DXF (1/100 mm) ────────
_MAP_ESPESSURA: list[tuple[float, int]] = [
    (0.35,  13),   # ≤ 0.35 pt  →  0.13 mm
    (0.75,  18),   # ≤ 0.75 pt  →  0.18 mm
    (1.10,  25),   # ≤ 1.10 pt  →  0.25 mm
    (1.60,  35),   # ≤ 1.60 pt  →  0.35 mm
    (2.20,  50),   # ≤ 2.20 pt  →  0.50 mm
    (3.00,  70),   # ≤ 3.00 pt  →  0.70 mm
    (1e9,  100),   # > 3.00 pt  →  1.00 mm
]

# ─── MAPEAMENTO: estilo de linha Matplotlib → linetype DXF ──────────────────
_MAP_LINETYPE: dict[str, str] = {
    '-':            'CONTINUOUS',
    'solid':        'CONTINUOUS',
    '--':           'DASHED',
    'dashed':       'DASHED',
    ':':            'DOTTED',
    'dotted':       'DOTTED',
    '-.':           'DASHDOT',
    'dashdot':      'DASHDOT',
    'dashdotdotted':'DIVIDE',
}

# Prefixos de camada por tipo de artista
_PREF_LINHA = 'LINHA'
_PREF_FILL  = 'FILL'
_PREF_TEXTO = 'TEXTO'
_PREF_SETA  = 'SETA'


# =============================================================================
# Funções utilitárias
# =============================================================================

def _true_color(cor) -> int:
    """Converte qualquer cor Matplotlib em inteiro True Color DXF (24 bits)."""
    try:
        r, g, b, *_ = mcolors.to_rgba(cor)
        return (int(r * 255) << 16) | (int(g * 255) << 8) | int(b * 255)
    except Exception:
        return 0xFFFFFF  # branco como fallback


def _lw_dxf(lw_pt: float) -> int:
    """Converte espessura de linha em pontos para código DXF (1/100 mm)."""
    for limite, codigo in _MAP_ESPESSURA:
        if lw_pt <= limite:
            return codigo
    return 100


def _ls_dxf(ls) -> str:
    """Converte estilo de linha Matplotlib para nome de linetype DXF."""
    if isinstance(ls, str):
        return _MAP_LINETYPE.get(ls.lower(), 'CONTINUOUS')
    if isinstance(ls, tuple):
        # Estilos customizados (offset, (on, off, ...)) → aproxima por DASHED
        return 'DASHED'
    return 'CONTINUOUS'


def _nome_camada(prefixo: str, tc: int) -> str:
    """Gera nome de camada: PREFIXO_RRGGBB (ex.: LINHA_FF9800)."""
    return f"{prefixo}_{tc:06X}"


def _garantir_camada(doc, nome: str, tc: int) -> None:
    """Cria a camada DXF se ainda não existir."""
    if nome not in doc.layers:
        doc.layers.new(
            name=nome,
            dxfattribs={
                'true_color': tc,
                'color': 7,       # índice ACI fallback (branco)
                'lineweight': -3, # padrão do bloco
            }
        )


def _disp_para_dxf(
    pts_display: np.ndarray,
    fig_h_px: float,
    dpi: float,
    escala: float,
) -> list[tuple[float, float]]:
    """
    Converte coordenadas de display (pixels) para coordenadas DXF (mm).

    O eixo Y é invertido: no display Y cresce para baixo, no DXF
    (e no Matplotlib data) Y cresce para cima.

    Retorna lista de tuplas (x_mm, y_mm) já escaladas.
    """
    pts = np.asarray(pts_display, dtype=float)
    if pts.ndim == 1:
        pts = pts.reshape(1, -1)
    mm_per_px = 25.4 / dpi * escala
    x_dxf = pts[:, 0] * mm_per_px
    y_dxf = (fig_h_px - pts[:, 1]) * mm_per_px  # inverte Y
    return list(zip(x_dxf.tolist(), y_dxf.tolist()))


def _eh_fundo(artista, ax) -> bool:
    """
    Retorna True para artistas que devem ser ignorados:
    background do eixo, invisíveis, totalmente transparentes.
    """
    if artista is ax.patch:
        return True
    if not artista.get_visible():
        return True
    try:
        a = artista.get_alpha()
        if a is not None and a < 0.01:
            return True
    except AttributeError:
        pass
    return False


def _cor_artista(artista, preferir_face: bool = False) -> tuple[int, float]:
    """
    Extrai a cor principal de um artista e retorna (true_color, alpha).
    Tenta edgecolor primeiro (ou facecolor se preferir_face=True).
    """
    try:
        if preferir_face:
            rgba = mcolors.to_rgba(artista.get_facecolor())
        else:
            rgba = mcolors.to_rgba(artista.get_edgecolor())
        return _true_color(rgba), rgba[3]
    except Exception:
        return 0xFFFFFF, 1.0


# =============================================================================
# Contexto de exportação
# =============================================================================

class _Ctx:
    """
    Contexto passado entre todos os handlers.
    Centraliza estado, configuração e acesso ao documento DXF.
    """

    __slots__ = (
        'doc', 'msp', 'fig_h_px', 'dpi', 'escala',
        'ignorar_textos', 'ignorar_fills',
        'altura_texto_base', 'fator_altura_texto',
    )

    def __init__(
        self,
        doc,
        msp,
        fig_h_px: float,
        dpi: float,
        escala: float,
        ignorar_textos: bool,
        ignorar_fills: bool,
        altura_texto_base: float,
        fator_altura_texto: float,
    ):
        self.doc               = doc
        self.msp               = msp
        self.fig_h_px          = fig_h_px
        self.dpi               = dpi
        self.escala            = escala
        self.ignorar_textos    = ignorar_textos
        self.ignorar_fills     = ignorar_fills
        self.altura_texto_base = altura_texto_base
        self.fator_altura_texto = fator_altura_texto

    def d2d(self, pts_display: np.ndarray) -> list[tuple[float, float]]:
        """Atalho: display → DXF."""
        return _disp_para_dxf(pts_display, self.fig_h_px, self.dpi, self.escala)

    def camada_linha(self, tc: int) -> str:
        nome = _nome_camada(_PREF_LINHA, tc)
        _garantir_camada(self.doc, nome, tc)
        return nome

    def camada_fill(self, tc: int) -> str:
        nome = _nome_camada(_PREF_FILL, tc)
        _garantir_camada(self.doc, nome, tc)
        return nome

    def camada_texto(self, tc: int) -> str:
        nome = _nome_camada(_PREF_TEXTO, tc)
        _garantir_camada(self.doc, nome, tc)
        return nome

    def camada_seta(self, tc: int) -> str:
        nome = _nome_camada(_PREF_SETA, tc)
        _garantir_camada(self.doc, nome, tc)
        return nome


# =============================================================================
# Handlers de artistas
# =============================================================================

def _draw_patch(patch, ax, ctx: _Ctx) -> None:
    """
    Handler genérico para qualquer Patch (FancyBboxPatch, Polygon,
    Rectangle, PathPatch, etc.).

    Usa o pipeline: get_path() + get_transform() → display → DXF.
    Exporta contorno como LWPOLYLINE e preenchimento como HATCH.
    """
    try:
        path      = patch.get_path()
        transform = patch.get_transform()

        if path is None or len(path.vertices) == 0:
            return

        verts_disp = transform.transform(path.vertices)
        pts        = ctx.d2d(verts_disp)

        if len(pts) < 2:
            return

        # ── Contorno ──────────────────────────────────────────────────────
        try:
            tc_e   = _true_color(patch.get_edgecolor())
            alpha_e = mcolors.to_rgba(patch.get_edgecolor())[3]
            lw     = _lw_dxf(patch.get_linewidth())
            ls     = _ls_dxf(patch.get_linestyle())
        except Exception:
            tc_e, alpha_e, lw, ls = 0xFFFFFF, 1.0, 13, 'CONTINUOUS'

        if alpha_e > 0.01 and lw > 0:
            cam = ctx.camada_linha(tc_e)
            ctx.msp.add_lwpolyline(
                pts, close=True,
                dxfattribs={
                    'layer':      cam,
                    'true_color': tc_e,
                    'lineweight': lw,
                    'linetype':   ls,
                }
            )

        # ── Preenchimento (HATCH) ──────────────────────────────────────────
        if not ctx.ignorar_fills and len(pts) >= 3:
            try:
                fc_rgba = mcolors.to_rgba(patch.get_facecolor())
                if fc_rgba[3] > 0.05:
                    tc_f  = _true_color(fc_rgba)
                    cam_f = ctx.camada_fill(tc_f)
                    h = ctx.msp.add_hatch(
                        color=2,
                        dxfattribs={'layer': cam_f, 'true_color': tc_f}
                    )
                    h.paths.add_polyline_path(
                        [tuple(p) for p in pts], is_closed=True
                    )
            except Exception:
                pass

    except Exception:
        pass


def _draw_circle(circle: mpatches.Circle, ax, ctx: _Ctx) -> None:
    """
    Exporta um Circle matplotlib como entidade CIRCLE DXF exata.

    Centro e raio são extraídos em coordenadas de dados e convertidos
    para display, garantindo que círculos em eixos com set_aspect('equal')
    permaneçam círculos perfeitos no DXF.
    """
    try:
        cx_d, cy_d = circle.get_center()
        r_d        = circle.get_radius()

        # Converte centro para display
        centro_disp  = ax.transData.transform([[cx_d, cy_d]])
        # Ponto na borda (direita) → permite calcular raio em pixels
        borda_disp   = ax.transData.transform([[cx_d + r_d, cy_d]])

        centro_dxf = ctx.d2d(centro_disp)[0]
        borda_dxf  = ctx.d2d(borda_disp)[0]

        r_dxf = abs(borda_dxf[0] - centro_dxf[0])
        if r_dxf < 1e-9:
            return

        tc_e   = _true_color(circle.get_edgecolor())
        alpha_e = mcolors.to_rgba(circle.get_edgecolor())[3]
        lw     = _lw_dxf(circle.get_linewidth())
        cam    = ctx.camada_linha(tc_e)

        if alpha_e > 0.01:
            ctx.msp.add_circle(
                center=centro_dxf,
                radius=r_dxf,
                dxfattribs={
                    'layer':      cam,
                    'true_color': tc_e,
                    'lineweight': lw,
                }
            )

        # ── Preenchimento circular (HATCH com borda elíptica) ──────────────
        if not ctx.ignorar_fills:
            try:
                fc_rgba = mcolors.to_rgba(circle.get_facecolor())
                if fc_rgba[3] > 0.05:
                    tc_f  = _true_color(fc_rgba)
                    cam_f = ctx.camada_fill(tc_f)
                    h = ctx.msp.add_hatch(
                        color=2,
                        dxfattribs={'layer': cam_f, 'true_color': tc_f}
                    )
                    h.paths.add_ellipse_edge(
                        center=centro_dxf,
                        semimajor_axis=(r_dxf, 0.0),
                        ratio=1.0,
                        ccw=True,
                    )
            except Exception:
                pass

    except Exception:
        pass


def _draw_line2d(line: matplotlib.lines.Line2D, ax, ctx: _Ctx) -> None:
    """
    Exporta uma Line2D como LWPOLYLINE(s) DXF.

    Usa get_transform() diretamente, o que cobre linhas normais E
    linhas com transforms mistos (axhline, axvline, axvspan, etc.).
    Segmentos separados por NaN são exportados como polylines distintas.
    """
    try:
        xdata = np.asarray(line.get_xdata(), dtype=float)
        ydata = np.asarray(line.get_ydata(), dtype=float)

        if len(xdata) < 2:
            return

        ls_str = line.get_linestyle()
        if ls_str in ('None', 'none', '') or ls_str is None:
            return  # linha invisível

        transform = line.get_transform()
        tc        = _true_color(line.get_color())
        lw        = _lw_dxf(line.get_linewidth())
        ls        = _ls_dxf(ls_str)
        cam       = ctx.camada_linha(tc)

        attribs = {
            'layer':      cam,
            'true_color': tc,
            'lineweight': lw,
            'linetype':   ls,
        }

        # Divide em segmentos nos pontos NaN
        segmento: list[tuple[float, float]] = []

        for x, y in zip(xdata, ydata):
            if np.isnan(x) or np.isnan(y):
                if len(segmento) >= 2:
                    pts_disp = transform.transform(segmento)
                    pts_dxf  = ctx.d2d(pts_disp)
                    ctx.msp.add_lwpolyline(pts_dxf, close=False, dxfattribs=attribs)
                segmento = []
            else:
                segmento.append((x, y))

        if len(segmento) >= 2:
            pts_disp = transform.transform(segmento)
            pts_dxf  = ctx.d2d(pts_disp)
            ctx.msp.add_lwpolyline(pts_dxf, close=False, dxfattribs=attribs)

    except Exception:
        pass


def _draw_text(txt: matplotlib.text.Text, ctx: _Ctx) -> None:
    """
    Exporta um Text como MTEXT DXF.

    A posição é obtida via txt.get_transform() + txt.get_position(),
    cobrindo tanto transData quanto transAxes.
    """
    if ctx.ignorar_textos:
        return

    try:
        conteudo = txt.get_text()
        if not conteudo.strip():
            return

        pos_data  = txt.get_position()
        transform = txt.get_transform()
        pos_disp  = transform.transform([pos_data])[0]
        pos_dxf   = ctx.d2d(np.array([pos_disp]))[0]

        tc  = _true_color(txt.get_color())
        cam = ctx.camada_texto(tc)

        # Altura do texto em mm
        try:
            fs         = txt.get_fontsize()   # em pontos
            altura_mm  = max(
                ctx.altura_texto_base,
                fs * ctx.fator_altura_texto
            )
        except Exception:
            altura_mm = ctx.altura_texto_base

        # Ponto de ancoragem MTEXT (1–9)
        ha = (txt.get_ha() or 'left').lower()
        va = (txt.get_va() or 'bottom').lower()
        ha_map = {'left': 1, 'center': 2, 'right': 3}
        va_map = {'top': 0, 'center': 3, 'bottom': 6,
                  'baseline': 6, 'center_baseline': 3}
        attachment = ha_map.get(ha, 1) + va_map.get(va, 6)

        # Rotação
        try:
            angulo = txt.get_rotation()  # graus
        except Exception:
            angulo = 0.0

        ctx.msp.add_mtext(
            conteudo,
            dxfattribs={
                'layer':            cam,
                'true_color':       tc,
                'char_height':      float(altura_mm),
                'insert':           pos_dxf,
                'attachment_point': attachment,
                'rotation':         float(angulo),
            }
        )

    except Exception:
        pass


def _draw_annotation(ann: matplotlib.text.Annotation, ctx: _Ctx) -> None:
    """
    Exporta uma Annotation (ax.annotate) como texto + seta DXF.

    O FancyArrowPatch interno é exportado via _draw_arrow_patch,
    garantindo que todas as setas de cota e carga sejam incluídas.
    """
    # Texto da anotação (pode ser vazio para setas puras)
    _draw_text(ann, ctx)

    # Seta interna
    if ann.arrow_patch is not None:
        _draw_arrow_patch(ann.arrow_patch, ctx)


def _draw_arrow_patch(arrow: mpatches.FancyArrowPatch, ctx: _Ctx) -> None:
    """
    Exporta um FancyArrowPatch como LWPOLYLINE(s) + HATCH(es) DXF.

    Usa _get_path_in_displaycoord() para obter os caminhos reais
    já em coordenadas de display (incluindo linha + pontas de seta).
    Cada sub-caminho (linha, seta esq., seta dir.) é exportado
    individualmente para preservar a geometria correta.
    """
    try:
        cor = arrow.get_edgecolor()
        if mcolors.to_rgba(cor)[3] < 0.01:
            cor = arrow.get_facecolor()
        tc  = _true_color(cor)
        lw  = _lw_dxf(arrow.get_linewidth())
        cam_l = ctx.camada_seta(tc)
        cam_f = ctx.camada_fill(tc)

        # _get_path_in_displaycoord() → (list[Path], list[bool])
        # Os paths já estão em coordenadas de display (pixels).
        paths_disp, _ = arrow._get_path_in_displaycoord()

        for path in paths_disp:
            if path is None or len(path.vertices) < 2:
                continue

            pts_dxf = ctx.d2d(path.vertices)

            # ── Contorno do caminho ────────────────────────────────────────
            ctx.msp.add_lwpolyline(
                pts_dxf, close=False,
                dxfattribs={
                    'layer':      cam_l,
                    'true_color': tc,
                    'lineweight': lw,
                }
            )

            # ── Preenchimento (pontas de seta) ────────────────────────────
            if not ctx.ignorar_fills and len(pts_dxf) >= 3:
                try:
                    fc_rgba = mcolors.to_rgba(arrow.get_facecolor())
                    if fc_rgba[3] > 0.05:
                        tc_f = _true_color(fc_rgba)
                        cam_fill = ctx.camada_fill(tc_f)
                        h = ctx.msp.add_hatch(
                            color=2,
                            dxfattribs={'layer': cam_fill, 'true_color': tc_f}
                        )
                        h.paths.add_polyline_path(
                            [tuple(p) for p in pts_dxf], is_closed=True
                        )
                except Exception:
                    pass

    except Exception:
        pass


def _draw_collection(coll, ax, ctx: _Ctx) -> None:
    """
    Exporta coleções Matplotlib para DXF:

    · PolyCollection  (fill_between / fill)   → LWPOLYLINE + HATCH
    · PathCollection  (scatter, PathCollect.) → LWPOLYLINE + HATCH
    · LineCollection  (vlines, hlines, etc.)  → LWPOLYLINE

    Cada sub-caminho da coleção é exportado individualmente.
    """
    try:
        paths      = coll.get_paths()
        transform  = coll.get_transform()
        is_line_c  = isinstance(coll, matplotlib.collections.LineCollection)

        cores_face = np.atleast_2d(coll.get_facecolor())
        cores_edge = np.atleast_2d(coll.get_edgecolor())

        for i, path in enumerate(paths):
            if len(path.vertices) < 2:
                continue

            try:
                verts_disp = transform.transform(path.vertices)
                pts_dxf    = ctx.d2d(verts_disp)
            except Exception:
                continue

            # ── Contorno ──────────────────────────────────────────────────
            cor_e = cores_edge[i % len(cores_edge)] if len(cores_edge) else [1, 1, 1, 1]
            alpha_e = cor_e[3] if len(cor_e) >= 4 else 1.0

            if alpha_e > 0.01 and len(pts_dxf) >= 2:
                tc_e = _true_color(cor_e)
                cam  = ctx.camada_linha(tc_e)
                try:
                    lws = coll.get_linewidth()
                    lw  = _lw_dxf(float(lws[0]) if hasattr(lws, '__len__') else float(lws))
                except Exception:
                    lw = 13
                ctx.msp.add_lwpolyline(
                    pts_dxf,
                    close=not is_line_c,
                    dxfattribs={
                        'layer':      cam,
                        'true_color': tc_e,
                        'lineweight': lw,
                    }
                )

            # ── Preenchimento ─────────────────────────────────────────────
            if not ctx.ignorar_fills and not is_line_c and len(pts_dxf) >= 3:
                cor_f   = cores_face[i % len(cores_face)] if len(cores_face) else [0, 0, 0, 0]
                alpha_f = cor_f[3] if len(cor_f) >= 4 else 0.0

                if alpha_f > 0.05:
                    tc_f  = _true_color(cor_f)
                    cam_f = ctx.camada_fill(tc_f)
                    try:
                        h = ctx.msp.add_hatch(
                            color=2,
                            dxfattribs={'layer': cam_f, 'true_color': tc_f}
                        )
                        h.paths.add_polyline_path(
                            [tuple(p) for p in pts_dxf], is_closed=True
                        )
                    except Exception:
                        pass

    except Exception:
        pass


# =============================================================================
# Dispatcher principal
# =============================================================================

def _processar_artista(artista, ax, ctx: _Ctx) -> None:
    """
    Roteia cada artista para o handler correto.

    Ordem de verificação:
    1. Filtros de exclusão (fundo, invisível)
    2. Annotation (antes de Text, pois é subclasse)
    3. Text genérico
    4. FancyArrowPatch autônomo
    5. Circle (antes de Patch genérico, para CIRCLE exato no DXF)
    6. Patch genérico (FancyBboxPatch, Polygon, Rectangle, PathPatch…)
    7. Line2D
    8. Collection (PolyCollection, PathCollection, LineCollection)
    """
    if _eh_fundo(artista, ax):
        return

    # 1. Annotation → texto + seta
    if isinstance(artista, matplotlib.text.Annotation):
        _draw_annotation(artista, ctx)
        return

    # 2. Text genérico
    if isinstance(artista, matplotlib.text.Text):
        _draw_text(artista, ctx)
        return

    # 3. FancyArrowPatch autônomo (não via annotate)
    if isinstance(artista, mpatches.FancyArrowPatch):
        _draw_arrow_patch(artista, ctx)
        return

    # 4. Circle → entidade CIRCLE DXF exata
    if isinstance(artista, mpatches.Circle):
        _draw_circle(artista, ax, ctx)
        return

    # 5. Patch genérico (captura FancyBboxPatch, Polygon, Rectangle, etc.)
    if isinstance(artista, mpatches.Patch):
        _draw_patch(artista, ax, ctx)
        return

    # 6. Line2D
    if isinstance(artista, matplotlib.lines.Line2D):
        _draw_line2d(artista, ax, ctx)
        return

    # 7. Coleções
    if isinstance(artista, matplotlib.collections.Collection):
        _draw_collection(artista, ax, ctx)
        return


# =============================================================================
# Função pública principal
# =============================================================================

def exportar_figura_para_dxf(fig, caminho_arquivo: str, **kwargs) -> None:
    """
    Exporta uma figura Matplotlib para o formato DXF (Drawing Exchange Format).

    Parâmetros
    ----------
    fig : matplotlib.figure.Figure
        Figura a exportar. Todos os eixos (axes) são processados.
    caminho_arquivo : str
        Caminho completo do arquivo DXF de saída (ex.: '/tmp/ponte.dxf').

    Keyword Arguments
    -----------------
    escala : float
        Fator de escala global aplicado a todas as coordenadas.
        Padrão: 1.0  (1 unidade DXF = 1 mm do tamanho físico da figura).
        Use 10.0 para exportar em 10× ampliado, 0.1 para reduzido.
    versao_dxf : str
        Versão do formato DXF. Padrão: 'R2010' (mínimo para True Color).
        Versões suportadas pelo ezdxf: 'R12', 'R2000', 'R2004',
        'R2007', 'R2010', 'R2013', 'R2018'.
    ignorar_textos : bool
        Se True, nenhum texto é exportado. Padrão: False.
    ignorar_fills : bool
        Se True, preenchimentos (HATCH) não são exportados.
        Padrão: False.
    altura_texto_base : float
        Altura mínima de texto em mm (DXF). Padrão: 1.0 mm.
    fator_altura_texto : float
        Fator de conversão: altura_mm = fontsize_pt × fator.
        Padrão: 0.353 (1 pt = 0.353 mm, conversão tipográfica exata).

    Raises
    ------
    ImportError
        Se o pacote 'ezdxf' não estiver instalado.
    RuntimeError
        Em caso de falha na criação ou gravação do arquivo DXF.
        Erros em artistas individuais são capturados silenciosamente
        para não interromper a exportação do restante da figura.

    Exemplo
    -------
    >>> from exportar_dxf import exportar_figura_para_dxf
    >>> fig = desenhar_dcl('biapoiada', [15.0, 15.0])
    >>> exportar_figura_para_dxf(fig, '/tmp/ponte.dxf', escala=1.0)
    """
    try:
        import ezdxf
    except ImportError:
        raise ImportError(
            "A biblioteca 'ezdxf' é necessária para exportar para DXF. "
            "Instale com: pip install ezdxf"
        )

    # ── Parâmetros de configuração ─────────────────────────────────────────
    escala             = float(kwargs.get('escala', 1.0))
    versao_dxf         = str(kwargs.get('versao_dxf', 'R2010'))
    ignorar_textos     = bool(kwargs.get('ignorar_textos', False))
    ignorar_fills      = bool(kwargs.get('ignorar_fills', False))
    altura_texto_base  = float(kwargs.get('altura_texto_base', 1.0))
    fator_altura_texto = float(kwargs.get('fator_altura_texto', 0.353))

    try:
        # ── 1. Força computação de layout (necessário para FancyArrowPatch) ─
        fig.canvas.draw()

        fig_w_px, fig_h_px = fig.get_size_inches() * fig.dpi
        dpi = float(fig.dpi)

        # ── 2. Cria documento DXF ──────────────────────────────────────────
        doc = ezdxf.new(versao_dxf)

        # Carrega linetypes ISO padrão (DASHED, DOTTED, DASHDOT, DIVIDE, etc.)
        ezdxf.setup_linetypes(doc)

        # Define unidades como milímetros no DXF
        doc.header['$INSUNITS'] = 4  # 4 = mm

        msp = doc.modelspace()

        ctx = _Ctx(
            doc               = doc,
            msp               = msp,
            fig_h_px          = fig_h_px,
            dpi               = dpi,
            escala            = escala,
            ignorar_textos    = ignorar_textos,
            ignorar_fills     = ignorar_fills,
            altura_texto_base = altura_texto_base,
            fator_altura_texto= fator_altura_texto,
        )

        # ── 3. Processa cada eixo ──────────────────────────────────────────
        for ax in fig.axes:
            for artista in ax.get_children():
                try:
                    _processar_artista(artista, ax, ctx)
                except Exception:
                    # Falhas pontuais não interrompem a exportação
                    pass

        # ── 4. Salva arquivo DXF ───────────────────────────────────────────
        doc.saveas(caminho_arquivo)

    except Exception as e:
        msg = str(e).strip() or f"{type(e).__name__}: {repr(e)}"
        raise RuntimeError(f"Falha na exportação DXF: {msg}") from e


# =============================================================================
# API de compatibilidade (mantida para não quebrar código legado)
# =============================================================================

def _cor_para_indice_dxf(cor_rgba) -> int:
    """
    [Legado] Retorna índice ACI: 7 (branco) ou 250 (preto).
    Prefira True Color via exportar_figura_para_dxf().
    """
    if cor_rgba is None or len(cor_rgba) < 3:
        return 7
    lum = 0.299 * cor_rgba[0] + 0.587 * cor_rgba[1] + 0.114 * cor_rgba[2]
    return 7 if lum > 0.5 else 250


def _espessura_para_dxf(lw_float: float) -> int:
    """[Legado] Alias para _lw_dxf()."""
    return _lw_dxf(lw_float)


# =============================================================================
# Bloco de testes
# =============================================================================

if __name__ == '__main__':
    import sys
    import os

    # Adiciona o diretório atual ao path para importar os módulos de desenho
    sys.path.insert(0, os.path.dirname(__file__))

    import matplotlib
    matplotlib.use('Agg')

    print("=" * 60)
    print("  BridgeCalc – Teste de Exportação DXF v3.0")
    print("=" * 60)

    testes = []

    # ── Teste 1: DCL biapoiada ─────────────────────────────────────────────
    try:
        from desenho_dcl import desenhar_dcl
        fig = desenhar_dcl('biapoiada', [15.0, 15.0])
        exportar_figura_para_dxf(fig, '/tmp/teste_dcl_biapoiada.dxf')
        print("  [OK] DCL biapoiada → /tmp/teste_dcl_biapoiada.dxf")
        testes.append(True)
    except Exception as e:
        print(f"  [ERRO] DCL biapoiada: {e}")
        testes.append(False)

    # ── Teste 2: DCL hiperestática com balanço ─────────────────────────────
    try:
        from desenho_dcl import desenhar_dcl
        fig = desenhar_dcl('hiperestatica_com_balanco', [30.0, 20.0, 3.0])
        exportar_figura_para_dxf(fig, '/tmp/teste_dcl_hiperestatica.dxf')
        print("  [OK] DCL hiperestática → /tmp/teste_dcl_hiperestatica.dxf")
        testes.append(True)
    except Exception as e:
        print(f"  [ERRO] DCL hiperestática: {e}")
        testes.append(False)

    # ── Teste 3: Esquema de cargas ─────────────────────────────────────────
    try:
        from desenho_esquema_cargas import desenhar_esquema_cargas
        fig = desenhar_esquema_cargas(Q1=450.0, q1=15.0, q2=5.0)
        exportar_figura_para_dxf(fig, '/tmp/teste_esquema_cargas.dxf')
        print("  [OK] Esquema cargas → /tmp/teste_esquema_cargas.dxf")
        testes.append(True)
    except Exception as e:
        print(f"  [ERRO] Esquema cargas: {e}")
        testes.append(False)

    # ── Teste 4: Ponte carregada ───────────────────────────────────────────
    try:
        from desenho_ponte_carregada import desenhar_ponte_carregada
        acoes = {
            "Carga Concentrada": [[450.0, 12.0, 18.0]],
            "Carga Distribuída": [[15.0, 0.0, 10.0], [5.0, 20.0, 30.0]],
        }
        fig = desenhar_ponte_carregada(
            tipo='isostatica_em_balanco',
            vaos=[14.0, 5.0],
            laje_transicao=3.0,
            acoes=acoes,
        )
        exportar_figura_para_dxf(fig, '/tmp/teste_ponte_carregada.dxf')
        print("  [OK] Ponte carregada → /tmp/teste_ponte_carregada.dxf")
        testes.append(True)
    except Exception as e:
        print(f"  [ERRO] Ponte carregada: {e}")
        testes.append(False)

    # ── Teste 5: Detalhamento de armadura ─────────────────────────────────
    try:
        from detalhamento_armadura import desenhar_detalhamento
        fig, *_ = desenhar_detalhamento(
            dados={'Tipo': 'T', 'bw': 25.0, 'h': 90.0, 'bf': 65.0, 'hf': 20.0},
            as_inf={'n': 8, 'diametro': 25.0},
            as_sup={'n': 4, 'diametro': 10.0},
        )
        exportar_figura_para_dxf(fig, '/tmp/teste_detalhamento.dxf')
        print("  [OK] Detalhamento armadura → /tmp/teste_detalhamento.dxf")
        testes.append(True)
    except Exception as e:
        print(f"  [ERRO] Detalhamento armadura: {e}")
        testes.append(False)

    print("=" * 60)
    ok = sum(testes)
    print(f"  Resultado: {ok}/{len(testes)} testes bem-sucedidos")
    print("=" * 60)
