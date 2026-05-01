#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detalhamento_armadura.py  –  v4.0
==================================
Detalhamento técnico completo de seções transversais com armadura de
cisalhamento (estribo NBR 6118) e armadura longitudinal (inferior e superior).

HISTÓRICO v4.0
──────────────
[FIX-1]  Distribuição SIMÉTRICA de barras em todas as camadas:
           · Camada 0: linspace(xc_min → xc_max) — espaçamento igualitário.
           · Camadas ≥ 1: pares simétricos das extremidades para o centro
             (n_esq = ceil(n_cam/2), n_dir = floor(n_cam/2)).
             Barra isolada sempre centrada em xc_ctr.
             Elimina o bug que acumulava todas as barras restantes à esquerda.
[FIX-2]  xlim_orig / ylim_orig recalculados com base no conteúdo real da
           figura (cotações + anotações + gancho), eliminando as margens
           infladas que encolhiam a seção a um tamanho mínimo.
[FIX-3]  Folga de vibrador corretamente aplicada a partir da camada 1 na
           armadura SUPERIOR, com a mesma estratégia simétrica do inferior.
[FIX-4]  x_ann / x_du reposicionados proporcionalmente a meia_w para não
           vazar para fora do xlim mesmo em seções estreitas.

HISTÓRICO v3.0 (mantido)
────────────────────────
[v3-1]   Zoom e pan estilo AutoCAD: scroll → zoom; MMB+drag → pan;
           duplo-clique → reset.
[v3-2]   ax_panel permanece fixo — zoom/pan afetam apenas ax.
[v3-3]   setup_zoom_pan(canvas) retornado como 4.º elemento da tupla.

Conformidade NBR 6118:
  ✔ Espaçamento horizontal mínimo ah entre faces de barras (item 18.3.2)
  ✔ Espaçamento vertical mínimo av entre camadas
  ✔ Folga central para vibrador (≥ φ_agulha) da 2ª camada em diante
  ✔ Barras distribuídas simetricamente em relação ao eixo da seção
  ✔ Estribo como polígono duplo (espessura real)
  ✔ Gancho a 135° com lh = max(10φ, 7 cm)
  ✔ Raio interno de dobra r_int = 2φ
"""

from __future__ import annotations

import math
from typing import Callable, Tuple

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
from matplotlib.patches import Polygon as MplPolygon, Circle as MplCircle
from matplotlib.lines import Line2D


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  BLOCO 1 — Geometria da seção transversal                                ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def _calcular_secao(dados: dict,
                    h_laje: float | None = None,
                    largura_colaborante: float | None = None) -> dict:
    """
    Calcula as propriedades geométricas da seção transversal.

    Parâmetros
    ----------
    dados : dict
        Dimensões da seção (ver formato em ``desenhar_detalhamento``).
    h_laje : float | None
        Espessura da laje colaborante (cm).
    largura_colaborante : float | None
        Largura colaborante da laje (cm).

    Retorna
    -------
    dict
        ``Area``, ``Area Longarina``, ``ycg``, ``h``, ``Ix``  (cm², cm, cm⁴).
    """
    tipo    = dados.get("Tipo")
    area    = 0.0
    ycg     = 0.0
    i_x     = 0.0
    h_total = dados.get("h", 0.0)
    comps: list[tuple[float, float, float]] = []   # (área, ycg_local, I_local)

    if tipo == "Retangular":
        b    = dados.get("bw") or dados.get("b", 0.0)
        h    = dados["h"]
        area = b * h
        ycg  = h / 2.0
        i_x  = b * h ** 3 / 12.0
        h_total = h

    elif tipo == "T":
        bw, h  = dados["bw"], dados["h"]
        bf, hf = dados["bf"], dados["hf"]
        hw     = h - hf
        for s in [{"b": bw, "h": hw, "y0": hw / 2.0},
                  {"b": bf, "h": hf, "y0": hw + hf / 2.0}]:
            ai = s["b"] * s["h"]
            comps.append((ai, s["y0"], s["b"] * s["h"] ** 3 / 12.0))
            area += ai

    elif tipo == "I":
        bw  = dados["bw"];  h   = dados["h"]
        btf = dados["btf"]; hft = dados["hft"]
        bfb = dados["bfb"]; hfb = dados["hfb"]
        hw  = h - hft - hfb
        for s in [{"b": bfb, "h": hfb, "y0": hfb / 2.0},
                  {"b": bw,  "h": hw,  "y0": hfb + hw / 2.0},
                  {"b": btf, "h": hft, "y0": h - hft / 2.0}]:
            ai = s["b"] * s["h"]
            comps.append((ai, s["y0"], s["b"] * s["h"] ** 3 / 12.0))
            area += ai
    else:
        raise ValueError(f"Tipo de seção '{tipo}' não suportado.")

    if tipo in ("T", "I"):
        ycg = sum(c[0] * c[1] for c in comps) / area
        i_x = sum(c[2] + c[0] * (c[1] - ycg) ** 2 for c in comps)

    area_long = area

    if largura_colaborante and h_laje:
        al    = largura_colaborante * h_laje
        yl    = h_total + h_laje / 2.0
        at    = area + al
        ycg_c = (area * ycg + al * yl) / at
        il    = largura_colaborante * h_laje ** 3 / 12.0
        i_x   = (i_x + area * (ycg - ycg_c) ** 2
                 + il  + al  * (yl  - ycg_c) ** 2)
        area    = at
        ycg     = ycg_c
        h_total = h_total + h_laje

    return {
        "Area":           area,
        "Area Longarina": area_long,
        "ycg":            ycg,
        "h":              h_total,
        "Ix":             i_x,
    }


def _poligono_secao(dados: dict) -> list[tuple[float, float]]:
    """Retorna vértices do polígono da seção (cm), y=0 na base inferior."""
    tipo = dados.get("Tipo")

    if tipo == "Retangular":
        b = dados.get("bw") or dados.get("b", 0.0)
        h = dados["h"]
        return [(-b / 2, 0), (b / 2, 0), (b / 2, h), (-b / 2, h)]

    if tipo == "T":
        bw, h  = dados["bw"], dados["h"]
        bf, hf = dados["bf"], dados["hf"]
        hw = h - hf
        return [
            (-bw / 2, 0),   (bw / 2, 0),
            (bw / 2, hw),   (bf / 2, hw), (bf / 2, h), (-bf / 2, h),
            (-bf / 2, hw),  (-bw / 2, hw),
        ]

    if tipo == "I":
        bw  = dados["bw"];  h   = dados["h"]
        btf = dados["btf"]; hft = dados["hft"]
        bfb = dados["bfb"]; hfb = dados["hfb"]
        return [
            (-bfb / 2, 0),     (bfb / 2, 0),
            (bfb / 2, hfb),    (bw / 2, hfb),   (bw / 2, h - hft),
            (btf / 2, h - hft),(btf / 2, h),     (-btf / 2, h),
            (-btf / 2, h-hft), (-bw / 2, h-hft), (-bw / 2, hfb),
            (-bfb / 2, hfb),
        ]

    return []


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  BLOCO 2 — Geometria do estribo                                          ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def _arc(cx: float, cy: float, R: float,
         t0_deg: float, t1_deg: float, n: int = 20) -> list[tuple]:
    """Arco circular de t0_deg a t1_deg com n pontos."""
    ts = np.linspace(math.radians(t0_deg), math.radians(t1_deg), n)
    return [(cx + R * math.cos(t), cy + R * math.sin(t)) for t in ts]


def _offset(pts: list | np.ndarray, d: float) -> list[tuple]:
    """Offset paralelo de polilinha aberta com miter limitado em 3×|d|."""
    pts = np.asarray(pts, dtype=float)
    n   = len(pts)
    res = []
    for i in range(n):
        if i == 0:
            seg = pts[1] - pts[0]
        elif i == n - 1:
            seg = pts[-1] - pts[-2]
        else:
            s1 = pts[i]   - pts[i - 1]; s1 /= max(np.linalg.norm(s1), 1e-12)
            s2 = pts[i + 1] - pts[i];   s2 /= max(np.linalg.norm(s2), 1e-12)
            seg = s1 + s2
        lng = np.linalg.norm(seg)
        if lng < 1e-12:
            res.append(tuple(pts[i]))
            continue
        seg /= lng
        nm    = np.array([-seg[1], seg[0]])
        miter = d
        if 0 < i < n - 1:
            s1_ = pts[i]     - pts[i-1]; s1_ /= max(np.linalg.norm(s1_), 1e-12)
            s2_ = pts[i + 1] - pts[i];   s2_ /= max(np.linalg.norm(s2_), 1e-12)
            dot = float(np.dot(s1_, s2_))
            sh  = math.sqrt(max(0.0, (1.0 - dot) / 2.0))
            if sh > 0.05:
                miter = float(np.clip(d / sh, -abs(d) * 3, abs(d) * 3))
        res.append((pts[i, 0] + miter * nm[0], pts[i, 1] + miter * nm[1]))
    return res


def _ring_cl(x_l, x_r, y_b, y_t, R, na=20) -> list[tuple]:
    """Linha de centro do anel retangular do estribo com cantos arredondados (CCW)."""
    ns  = 6
    pts: list[tuple] = []
    pts += [(x_l, y) for y in np.linspace(y_t - R, y_b + R, ns)]
    pts += _arc(x_l + R, y_b + R, R, 180, 270, na)
    pts += [(x,   y_b) for x in np.linspace(x_l + R, x_r - R, ns)]
    pts += _arc(x_r - R, y_b + R, R, 270, 360, na)
    pts += [(x_r, y)   for y in np.linspace(y_b + R, y_t - R, ns)]
    pts += _arc(x_r - R, y_t - R, R, 0,   90,  na)
    pts += [(x,   y_t) for x in np.linspace(x_r - R, x_l + R, ns)]
    pts += _arc(x_l + R, y_t - R, R, 90,  180, na)
    pts.append(pts[0])
    return pts


def _hook_cl(x_l, y_t, R, lh) -> list[tuple]:
    """Linha de centro do gancho a 135° no canto superior-esquerdo."""
    cx, cy = x_l + R, y_t - R
    arc    = _arc(cx, cy, R, 90, 225, 32)
    end    = np.array(arc[-1])
    tip    = end + lh * np.array([
        math.cos(math.radians(315)), math.sin(math.radians(315))])
    return arc + [tuple(tip)]


def _tube(pts, phi):
    """Retorna (outer, inner): duas bordas paralelas distantes phi/2."""
    return _offset(pts, phi / 2.0), _offset(pts, -phi / 2.0)


def _open_tube_poly(pts, phi) -> list[tuple]:
    """Polígono fechado representando tubo com semi-círculo em cada extremidade."""
    outer, inner = _tube(pts, phi)
    tip  = np.array(pts[-1])
    td   = np.array(pts[-1]) - np.array(pts[-2])
    td  /= max(np.linalg.norm(td), 1e-12)
    tp   = np.array([-td[1], td[0]])
    a0   = math.degrees(math.atan2(tp[1], tp[0]))
    cap_tip = [(tip[0] + (phi / 2) * math.cos(math.radians(a)),
                tip[1] + (phi / 2) * math.sin(math.radians(a)))
               for a in np.linspace(a0, a0 - 180, 12)]
    base = np.array(pts[0])
    bd   = np.array(pts[1]) - np.array(pts[0])
    bd  /= max(np.linalg.norm(bd), 1e-12)
    bp   = np.array([-bd[1], bd[0]])
    a1   = math.degrees(math.atan2(bp[1], bp[0]))
    cap_base = [(base[0] + (phi / 2) * math.cos(math.radians(a)),
                 base[1] + (phi / 2) * math.sin(math.radians(a)))
                for a in np.linspace(a1 + 180, a1, 12)]
    return outer + cap_tip + list(reversed(inner)) + cap_base


def _estribo_dims(dados: dict, c: float, phi_est: float):
    """
    Calcula as dimensões de referência (linha de centro) do estribo.

    Retorna
    -------
    (x_l, x_r, y_b, y_t, R_cl, lh)
        Coordenadas das linhas de centro do anel, raio interno e comprimento
        do gancho (todos em cm).
    """
    d    = c + phi_est / 2.0
    R_cl = max(2.0 * phi_est + phi_est / 2.0, 0.05)
    lh   = max(10.0 * phi_est, 7.0)
    tipo = dados.get("Tipo")
    bw   = dados.get("bw") or dados.get("b", 0.0)

    if tipo == "Retangular":
        h = dados["h"]
        x_l, x_r = -bw / 2.0 + d, bw / 2.0 - d
        y_b, y_t =  d,            h - d
    elif tipo == "T":
        h = dados["h"]
        x_l, x_r = -bw / 2.0 + d, bw / 2.0 - d
        y_b, y_t =  d,            h - d
    elif tipo == "I":
        h   = dados["h"]
        hfb = dados["hfb"]; hft = dados["hft"]
        x_l, x_r = -bw / 2.0 + d, bw / 2.0 - d
        y_b, y_t =  hfb + d,      h - hft - d
    else:
        raise ValueError(f"Tipo '{tipo}' não suportado em _estribo_dims.")

    hw   = (x_r - x_l) / 2.0
    hh   = (y_t - y_b) / 2.0
    R_cl = max(0.05, min(R_cl, hw - 0.05, hh - 0.05))
    return x_l, x_r, y_b, y_t, R_cl, lh


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  BLOCO 3 — Posicionamento das armaduras longitudinais                    ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def _calcular_zonas(dados: dict,
                    c: float,
                    phi_est: float,
                    h_laje: float | None,
                    lc: float | None) -> tuple[dict, dict]:
    """
    Determina os limites espaciais (zona) de posicionamento das barras.

    A zona define o retângulo disponível dentro do estribo para cada grupo
    de armadura (inferior e superior).

    Parâmetros
    ----------
    dados : dict
        Dimensões da seção.
    c : float
        Cobrimento nominal (cm).
    phi_est : float
        Diâmetro do estribo (cm).
    h_laje : float | None
        Espessura da laje colaborante (cm).
    lc : float | None
        Largura colaborante (cm).

    Retorna
    -------
    (zona_inf, zona_sup)
        Dicionários com ``x_l``, ``x_r``, ``y_0``, ``direcao`` e ``tag``.
        ``direcao='up'``  → camadas crescem em +y (inferior).
        ``direcao='down'``→ camadas crescem em −y (superior).
    """
    tipo  = dados.get("Tipo")
    h     = dados["h"]
    h_tot = h + (h_laje or 0.0)
    bw    = dados.get("bw") or dados.get("b", 0.0)
    # Deslocamento da face externa ao centro do estribo: c + φₜ/2
    # → face interna do estribo em: c + φₜ  (a partir da face do concreto)
    d_est = c + phi_est

    # ── Seção Retangular ──────────────────────────────────────────────────
    if tipo == "Retangular":
        zona_inf = dict(
            x_l=-bw / 2.0 + d_est, x_r=bw / 2.0 - d_est,
            y_0=d_est, direcao="up", tag="Ret-inf",
        )
        if lc and h_laje:
            zona_sup = dict(
                x_l=-lc / 2.0 + c, x_r=lc / 2.0 - c,
                y_0=h_tot - c, direcao="down", tag="Ret-sup-laje",
            )
        else:
            zona_sup = dict(
                x_l=-bw / 2.0 + d_est, x_r=bw / 2.0 - d_est,
                y_0=h - d_est, direcao="down", tag="Ret-sup",
            )

    # ── Seção T ───────────────────────────────────────────────────────────
    elif tipo == "T":
        bf, hf = dados["bf"], dados["hf"]
        zona_inf = dict(
            x_l=-bw / 2.0 + d_est, x_r=bw / 2.0 - d_est,
            y_0=d_est, direcao="up", tag="T-inf",
        )
        if lc and h_laje:
            zona_sup = dict(
                x_l=-lc / 2.0 + c, x_r=lc / 2.0 - c,
                y_0=h_tot - c, direcao="down", tag="T-sup-laje",
            )
        else:
            zona_sup = dict(
                x_l=-bf / 2.0 + d_est, x_r=bf / 2.0 - d_est,
                y_0=h - d_est, direcao="down", tag="T-sup-mesa",
            )

    # ── Seção I ───────────────────────────────────────────────────────────
    elif tipo == "I":
        btf, hft = dados["btf"], dados["hft"]
        bfb, hfb = dados["bfb"], dados["hfb"]
        zona_inf = dict(
            x_l=-bfb / 2.0 + d_est, x_r=bfb / 2.0 - d_est,
            y_0=d_est, direcao="up", tag="I-inf",
        )
        if lc and h_laje:
            zona_sup = dict(
                x_l=-lc / 2.0 + c, x_r=lc / 2.0 - c,
                y_0=h_tot - c, direcao="down", tag="I-sup-laje",
            )
        else:
            zona_sup = dict(
                x_l=-btf / 2.0 + d_est, x_r=btf / 2.0 - d_est,
                y_0=h - d_est, direcao="down", tag="I-sup-mesa",
            )
    else:
        raise ValueError(f"Tipo '{tipo}' não suportado em _calcular_zonas.")

    return zona_inf, zona_sup


def _distribuir_barras(
    n: int,
    phi: float,
    zona: dict,
    ah_min: float,
    av: float,
    folga_vibrador: float,
) -> list[tuple[float, float]]:
    """
    Distribui **n** barras de diâmetro **phi** em camadas dentro da zona,
    respeitando os espaçamentos mínimos da NBR 6118 e **simetria de eixo**.

    Algoritmo (NBR 6118, item 18.3.2)
    ----------------------------------
    **Camada 0 (primeira):**
      Barras distribuídas com espaçamento igualitário em toda a largura
      disponível via ``linspace(xc_min, xc_max, n_cam)``.
      Máximo de barras: maior ``n_max`` tal que ``(n_max−1)·(φ+ah_min) ≤ larg``.

    **Camadas k ≥ 1 (folga de vibrador):**
      Requer passagem livre central ≥ ``folga_vibrador``.
      Barras distribuídas em **pares simétricos** das extremidades para o
      centro::

          n_esq = ⌈n_cam/2⌉   (lado que recebe a barra extra, se n ímpar)
          n_dir = ⌊n_cam/2⌋   (lado espelhado)

          Posições esq:  xc_min + i·(φ + ah_min),  i = 0..n_esq−1
          Posições dir:  xc_max − i·(φ + ah_min),  i = 0..n_dir−1

      Barra **isolada** (n_cam = 1) → centrada em xc_ctr (vibrador passa
      pelos dois lados).

    Parâmetros
    ----------
    n : int
        Número total de barras a distribuir.
    phi : float
        Diâmetro das barras (cm).
    zona : dict
        Dicionário com ``x_l``, ``x_r``, ``y_0``, ``direcao``.
    ah_min : float
        Espaçamento horizontal mínimo LIVRE entre faces de barras (cm).
    av : float
        Espaçamento vertical mínimo LIVRE entre camadas (cm).
    folga_vibrador : float
        Largura livre mínima no centro para vibrador, da 2ª camada em diante (cm).

    Retorna
    -------
    list[tuple[float, float]]
        Coordenadas (x, y) dos centros das barras, em cm.
    """
    if n <= 0:
        return []

    r     = phi / 2.0
    sign  = 1 if zona["direcao"] == "up" else -1

    # ── Limites dos centros de barra (encostadas na face interna do estribo)
    xc_min = zona["x_l"] + r
    xc_max = zona["x_r"] - r
    xc_ctr = (xc_min + xc_max) / 2.0
    larg   = max(xc_max - xc_min, 0.0)

    if xc_max < xc_min:                  # zona estreita demais → barra central
        xc_min = xc_max = xc_ctr

    # Posição y da primeira barra (encostada na face interna do estribo)
    y0c = zona["y_0"] + sign * r

    # Passo mínimo centro-a-centro
    passo = phi + ah_min

    posicoes: list[tuple[float, float]] = []
    n_rest  = n
    camada  = 0
    MAX_CAMADAS = 60     # guarda contra loop infinito

    while n_rest > 0 and camada < MAX_CAMADAS:
        y_c = y0c + sign * camada * (phi + av)

        # ── Decide se aplica folga de vibrador ──────────────────────────────
        # Requisito: camada ≥ 1 E largura suficiente para gap central + 2 barras
        usar_folga = (camada >= 1) and (larg >= folga_vibrador + 2.0 * phi + 1e-6)

        if not usar_folga:
            # ── Camada sem folga: espaçamento igualitário por toda a largura ──
            if larg < 1e-6:
                n_cam = 1
                xs: list[float] = [xc_ctr]
            else:
                # Maior n tal que (n−1)·passo ≤ larg
                n_max = max(1, int(larg / passo) + 1)
                while n_max > 1 and (n_max - 1) * passo > larg + 1e-6:
                    n_max -= 1
                n_cam = min(n_rest, n_max)
                if n_cam == 1:
                    xs = [xc_ctr]
                else:
                    # linspace garante espaçamento ≥ passo (por construção)
                    xs = list(np.linspace(xc_min, xc_max, n_cam))

        else:
            # ── Camadas ≥ 1: pares simétricos com folga central ──────────────
            semi = (larg - folga_vibrador) / 2.0    # semilargura por lado

            # Máximo de barras por lado: maior n_lado tal que (n_lado−1)·passo ≤ semi
            n_lado = max(1, int(semi / passo) + 1)
            while n_lado > 1 and (n_lado - 1) * passo > semi + 1e-6:
                n_lado -= 1

            n_cam = min(n_rest, 2 * n_lado)

            if n_cam == 1:
                # Barra isolada: centrada (vibrador passa pelos dois lados)
                xs = [xc_ctr]
            else:
                # Distribuição simétrica em pares das extremidades para o centro
                # n_esq recebe a barra extra quando n_cam é ímpar
                n_esq = (n_cam + 1) // 2    # ceil(n_cam / 2)
                n_dir = n_cam // 2           # floor(n_cam / 2)

                esq_xs = [xc_min + i * passo for i in range(n_esq)]
                dir_xs = [xc_max - i * passo for i in range(n_dir)]
                xs     = esq_xs + dir_xs

        for x in xs:
            posicoes.append((float(x), float(y_c)))

        n_rest -= len(xs)

        if len(xs) == 0:
            break       # segurança: zona impossível

        camada += 1

    return posicoes


def _cg_grupo(posicoes: list[tuple[float, float]], phi: float) -> tuple[float, float]:
    """
    Calcula o CG (ycg) e área total de um grupo de barras.

    Retorna (0.0, 0.0) se a lista estiver vazia.
    """
    if not posicoes:
        return 0.0, 0.0
    ycg  = sum(p[1] for p in posicoes) / len(posicoes)
    area = math.pi * phi ** 2 / 4.0 * len(posicoes)
    return ycg, area


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  BLOCO 4 — Paleta de cores (dark theme)                                  ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

_C: dict[str, str] = dict(
    fundo    = "#0D0D0D",
    concreto = "#2C2C2C",
    borda    = "#606060",
    laje     = "#1A2E3E",
    laje_brd = "#3A6080",
    estribo  = "#D4843A",
    inf      = "#E05050",
    sup      = "#5090D8",
    cota     = "#505050",
    texto    = "#D0D0D0",
    painel   = "#111111",
    painel_b = "#333333",
    accent   = "#888888",
)


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  BLOCO 5 — Função principal de detalhamento                              ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def desenhar_detalhamento(
    dados: dict,
    as_inf: dict | None = None,
    as_sup: dict | None = None,
    c: float = 3.0,
    phi_estribo: float = 8.0,
    ah_min_inf: float = 2.0,
    ah_min_sup: float = 2.0,
    av_inf: float = 2.0,
    av_sup: float = 2.0,
    folga_vibrador: float = 6.0,
    h_laje: float | None = None,
    largura_colaborante: float | None = None,
    exibir_cotas: bool = True,
    dpi: int = 100,
    tamanho_fixo_qframe: bool = True,
) -> Tuple["Figure", float, float, Callable]:
    """
    Gera o detalhamento técnico completo da seção transversal.

    Parâmetros de entrada
    ----------------------
    dados : dict
        Geometria da seção::

            Retangular → {"Tipo": "Retangular", "bw": float, "h": float}
            T          → {"Tipo": "T", "bw":…, "h":…, "bf":…, "hf":…}
            I          → {"Tipo": "I", "bw":…, "h":…,
                           "btf":…, "hft":…, "bfb":…, "hfb":…}

        Todas as dimensões em **cm**.
    as_inf / as_sup : dict | None
        ``{"n": int, "diametro": float}`` — diâmetro em **mm**.
    c : float
        Cobrimento nominal (cm).
    phi_estribo : float
        Diâmetro do estribo (mm).
    ah_min_inf / ah_min_sup : float
        Espaçamento horizontal mínimo livre entre faces (cm). Conforme
        NBR 6118 item 18.3.2: max(2 cm, φ, 1,2·φ_ag).
    av_inf / av_sup : float
        Espaçamento vertical mínimo livre entre camadas (cm).
    folga_vibrador : float
        Largura livre central para vibrador, aplicada na 2ª camada em
        diante tanto na armadura inferior quanto na superior (cm).
    h_laje / largura_colaborante : float | None
        Laje colaborante (cm).
    exibir_cotas : bool
        Ativa cotagem dimensional.
    dpi : int
        Resolução da figura (px/polegada).
    tamanho_fixo_qframe : bool
        ``True``  → 951 × 551 px (embutida em QFrame 951×551).
        ``False`` → tamanho dinâmico proporcional ao tamanho da seção.

    Retorna
    -------
    (fig, d_prime_inf, d_prime_sup, setup_zoom_pan)
        fig            : ``matplotlib.figure.Figure``
        d_prime_inf    : float — distância face inferior → CG arm. inf (cm).
        d_prime_sup    : float — distância face superior → CG arm. sup (cm).
        setup_zoom_pan : ``callable(canvas)`` — conecta zoom/pan ao canvas Qt.
    """

    # ── 0. Parâmetros derivados ────────────────────────────────────────────
    phi_est = phi_estribo / 10.0        # mm → cm
    phi_i   = (as_inf["diametro"] / 10.0) if as_inf else 0.0
    phi_s   = (as_sup["diametro"] / 10.0) if as_sup else 0.0
    tipo    = dados.get("Tipo")
    h       = dados["h"]
    lc      = largura_colaborante
    h_tot   = h + (h_laje or 0.0)
    bw      = dados.get("bw") or dados.get("b", 0.0)

    # Meia-largura máxima da seção (para dimensionar o campo de desenho)
    meia_w = max(
        dados.get("bf",  0.0) / 2.0,
        dados.get("btf", 0.0) / 2.0,
        dados.get("bfb", 0.0) / 2.0,
        bw / 2.0,
        (lc or 0.0) / 2.0,
        20.0,       # mínimo absoluto para evitar vistas muito comprimidas
    )

    # ── 1. Geometria do estribo ────────────────────────────────────────────
    x_l, x_r, y_b, y_t, R_cl, lh = _estribo_dims(dados, c, phi_est)

    # ── 2. Zonas e distribuição das armaduras ──────────────────────────────
    zona_inf, zona_sup = _calcular_zonas(dados, c, phi_est, h_laje, lc)

    pos_inf = (
        _distribuir_barras(
            as_inf["n"], phi_i, zona_inf,
            ah_min_inf, av_inf, folga_vibrador,
        )
        if (as_inf and as_inf.get("n", 0) > 0) else []
    )
    pos_sup = (
        _distribuir_barras(
            as_sup["n"], phi_s, zona_sup,
            ah_min_sup, av_sup, folga_vibrador,
        )
        if (as_sup and as_sup.get("n", 0) > 0) else []
    )

    # ── 3. CG e distâncias d' ─────────────────────────────────────────────
    if pos_inf:
        ycg_inf, area_inf = _cg_grupo(pos_inf, phi_i)
    else:
        ycg_inf  = c + phi_est + phi_i / 2.0
        area_inf = 0.0

    if pos_sup:
        ycg_sup, area_sup = _cg_grupo(pos_sup, phi_s)
    else:
        ycg_sup  = h_tot - c - phi_est - phi_s / 2.0
        area_sup = 0.0

    d_prime_inf = ycg_inf               # distância face inf → CG arm. inf
    d_prime_sup = h_tot - ycg_sup       # distância face sup → CG arm. sup
    d_util      = h_tot - d_prime_inf   # altura útil

    # ── 4. Criação da figura ───────────────────────────────────────────────
    if tamanho_fixo_qframe:
        fig      = Figure(figsize=(9.51, 5.51), facecolor=_C["fundo"], dpi=dpi)
        ax       = fig.add_axes([0.01, 0.06, 0.62, 0.88])
        ax_panel = fig.add_axes([0.64, 0.06, 0.35, 0.88])
    else:
        # Tamanho dinâmico: cresce proporcionalmente com a seção
        fig_w = float(np.clip(2.0 * meia_w * 0.20 + 12.0, 12.0, 28.0))
        fig   = Figure(figsize=(fig_w, 8.0), facecolor=_C["fundo"], dpi=dpi)
        ax       = fig.add_axes([0.03, 0.06, 0.60, 0.88])
        ax_panel = fig.add_axes([0.64, 0.06, 0.34, 0.88])

    ax.set_facecolor(_C["fundo"])
    ax_panel.set_facecolor(_C["painel"])
    ax_panel.set_xlim(0, 1)
    ax_panel.set_ylim(0, 1)
    ax_panel.axis("off")

    # ═════════════════════════════════════════════════════════════════════
    #  SEÇÃO 1 — Polígono do concreto
    # ═════════════════════════════════════════════════════════════════════
    poly = _poligono_secao(dados)
    ax.add_patch(MplPolygon(
        poly, closed=True,
        facecolor=_C["concreto"], edgecolor=_C["borda"], lw=1.4, zorder=2,
    ))

    # ═════════════════════════════════════════════════════════════════════
    #  SEÇÃO 2 — Laje colaborante
    # ═════════════════════════════════════════════════════════════════════
    if lc and h_laje:
        ax.add_patch(mpatches.Rectangle(
            (-lc / 2.0, h), lc, h_laje,
            facecolor=_C["laje"], edgecolor=_C["laje_brd"],
            lw=1.2, alpha=0.88, zorder=2,
        ))
        for xi in np.arange(-lc / 2.0 + 4.0, lc / 2.0, 8.0):
            ax.plot([xi, xi + h_laje], [h, h + h_laje],
                    color=_C["laje_brd"], lw=0.35, alpha=0.30, zorder=3)
        x_ifc = max(dados.get("bf", bw) / 2.0, bw / 2.0)
        ax.plot([-x_ifc, x_ifc], [h, h],
                color=_C["borda"], lw=0.75, ls="--", alpha=0.65, zorder=4)

    # ═════════════════════════════════════════════════════════════════════
    #  SEÇÃO 3 — Estribo: anel (polígono duplo com espessura real)
    # ═════════════════════════════════════════════════════════════════════
    ring         = _ring_cl(x_l, x_r, y_b, y_t, R_cl)
    outer, inner = _tube(ring, phi_est)
    ax.add_patch(MplPolygon(outer, closed=True,
                             facecolor=_C["estribo"], edgecolor="none", zorder=5))
    ax.add_patch(MplPolygon(inner, closed=True,
                             facecolor=_C["concreto"], edgecolor="none", zorder=5))
    ax.add_patch(MplPolygon(outer, closed=True, facecolor="none",
                             edgecolor="white", lw=0.30, alpha=0.28, zorder=6))

    # ═════════════════════════════════════════════════════════════════════
    #  SEÇÃO 4 — Estribo: gancho a 135°
    # ═════════════════════════════════════════════════════════════════════
    hook      = _hook_cl(x_l, y_t, R_cl, lh)
    hook_poly = _open_tube_poly(hook, phi_est)
    ax.add_patch(MplPolygon(hook_poly, closed=True,
                             facecolor=_C["estribo"], edgecolor="none", zorder=6))

    # ═════════════════════════════════════════════════════════════════════
    #  SEÇÃO 5 — Armaduras longitudinais
    # ═════════════════════════════════════════════════════════════════════
    for (x, y) in pos_inf:
        ax.add_patch(MplCircle((x, y), phi_i / 2.0,
                               facecolor=_C["inf"], edgecolor="white",
                               lw=0.45, zorder=7))
    for (x, y) in pos_sup:
        ax.add_patch(MplCircle((x, y), phi_s / 2.0,
                               facecolor=_C["sup"], edgecolor="white",
                               lw=0.45, zorder=7))

    # ═════════════════════════════════════════════════════════════════════
    #  SEÇÃO 6 — Linhas tracejadas de CG das armaduras
    # ═════════════════════════════════════════════════════════════════════
    x_cg_ext = meia_w * 0.80
    if pos_inf:
        ax.plot([-x_cg_ext, x_cg_ext], [ycg_inf, ycg_inf],
                color=_C["inf"], lw=0.85, ls=(0, (5, 4)), alpha=0.55, zorder=4)
    if pos_sup:
        ax.plot([-x_cg_ext, x_cg_ext], [ycg_sup, ycg_sup],
                color=_C["sup"], lw=0.85, ls=(0, (5, 4)), alpha=0.55, zorder=4)

    # ═════════════════════════════════════════════════════════════════════
    #  SEÇÃO 7 — Anotações d' e d_util (colunas laterais direitas)
    #
    #  Posicionamento proporcional a meia_w para caber sempre no xlim.
    #  x_ann → seta d'inf / d'sup
    #  x_du  → seta d_util
    # ═════════════════════════════════════════════════════════════════════
    x_ann = meia_w + 3.5
    x_du  = x_ann  + 11.0

    if pos_inf:
        ax.annotate("", xy=(x_ann, 0), xytext=(x_ann, ycg_inf),
                    arrowprops=dict(arrowstyle="<->", color=_C["inf"], lw=1.0))
        ax.text(x_ann + 1.0, ycg_inf / 2.0,
                f"d'ᵢ={d_prime_inf:.2f} cm", color=_C["inf"], fontsize=6.8,
                va="center",
                bbox=dict(boxstyle="round,pad=0.22",
                          facecolor="#1A1A1A", edgecolor=_C["inf"], alpha=0.88))

    if pos_sup:
        ax.annotate("", xy=(x_ann, h_tot), xytext=(x_ann, ycg_sup),
                    arrowprops=dict(arrowstyle="<->", color=_C["sup"], lw=1.0))
        ax.text(x_ann + 1.0, (h_tot + ycg_sup) / 2.0,
                f"d'ₛ={d_prime_sup:.2f} cm", color=_C["sup"], fontsize=6.8,
                va="center",
                bbox=dict(boxstyle="round,pad=0.22",
                          facecolor="#1A1A1A", edgecolor=_C["sup"], alpha=0.88))

    if pos_inf:
        ax.annotate("", xy=(x_du, 0), xytext=(x_du, ycg_inf),
                    arrowprops=dict(arrowstyle="<->", color=_C["texto"], lw=0.9))
        ax.text(x_du + 1.0, ycg_inf / 2.0,
                f"d={d_util:.2f} cm", color=_C["texto"], fontsize=6.8,
                va="center",
                bbox=dict(boxstyle="round,pad=0.22",
                          facecolor="#141414", edgecolor="#505050", alpha=0.88))

    # ═════════════════════════════════════════════════════════════════════
    #  SEÇÃO 8 — Indicador de cobrimento
    # ═════════════════════════════════════════════════════════════════════
    if exibir_cotas:
        x_face   = (-dados.get("bfb", bw) / 2.0 if tipo == "I" else -bw / 2.0)
        x_est_in = x_face + c + phi_est
        y_cob    = c + phi_est + (phi_i / 2.0 if phi_i else 0.5)
        ax.annotate("", xy=(x_face, y_cob), xytext=(x_est_in, y_cob),
                    arrowprops=dict(arrowstyle="<->", color=_C["accent"], lw=0.7))
        ax.text((x_face + x_est_in) / 2.0, y_cob + 1.5,
                f"c={c:.0f}",
                color=_C["accent"], ha="center", va="bottom", fontsize=6.2)

    # ═════════════════════════════════════════════════════════════════════
    #  SEÇÃO 9 — Cotagem dimensional
    # ═════════════════════════════════════════════════════════════════════
    # Offsets fixos de cotagem:
    #   y_bot = posição da cota horizontal inferior
    #   x_esq = offset horizontal das cotas verticais (a partir da face da seção)
    y_bot  = -10.0
    x_esq  = -meia_w - 10.0

    if exibir_cotas:

        def _tick_h(x, y, sz=1.2):
            ax.plot([x, x], [y - sz, y + sz], color=_C["cota"], lw=0.65)

        def _tick_v(x, y, sz=1.2):
            ax.plot([x - sz, x + sz], [y, y], color=_C["cota"], lw=0.65)

        def cota_h(x1, x2, y_pos, label, yoff=0.0):
            """Cotagem horizontal entre x1 e x2, posicionada em y_pos+yoff."""
            y = y_pos + yoff
            ax.plot([x1, x1], [y_pos, y], color=_C["cota"], lw=0.45, ls=":")
            ax.plot([x2, x2], [y_pos, y], color=_C["cota"], lw=0.45, ls=":")
            ax.annotate("", xy=(x1, y), xytext=(x2, y),
                        arrowprops=dict(arrowstyle="<->",
                                        color=_C["cota"], lw=0.75))
            _tick_h(x1, y)
            _tick_h(x2, y)
            ax.text((x1 + x2) / 2.0, y + 1.5, label,
                    color=_C["texto"], ha="center", va="bottom", fontsize=7.2)

        def cota_v(y1, y2, x_pos, label, xoff=0.0):
            """Cotagem vertical entre y1 e y2, posicionada em x_pos+xoff."""
            x = x_pos + xoff
            ax.plot([x_pos, x], [y1, y1], color=_C["cota"], lw=0.45, ls=":")
            ax.plot([x_pos, x], [y2, y2], color=_C["cota"], lw=0.45, ls=":")
            ax.annotate("", xy=(x, y1), xytext=(x, y2),
                        arrowprops=dict(arrowstyle="<->",
                                        color=_C["cota"], lw=0.75))
            _tick_v(x, y1)
            _tick_v(x, y2)
            ax.text(x - 1.8, (y1 + y2) / 2.0, label,
                    color=_C["texto"], ha="right", va="center",
                    fontsize=7.2, rotation=90)

        if tipo == "Retangular":
            cota_h(-bw / 2.0, bw / 2.0, 0,   f"bw={bw:.0f}", y_bot)
            cota_v(0, h,      -bw / 2.0, f"h={h:.0f}",  x_esq)

        elif tipo == "T":
            bf, hf = dados["bf"], dados["hf"]
            hw = h - hf
            cota_h(-bw / 2.0, bw / 2.0, 0,  f"bw={bw:.0f}", y_bot)
            cota_h(-bf / 2.0, bf / 2.0, h,  f"bf={bf:.0f}", 10)
            cota_v(0,  hw, -bf / 2.0, f"hw={hw:.0f}", x_esq)
            cota_v(hw, h,  -bf / 2.0, f"hf={hf:.0f}", x_esq - 9)

        elif tipo == "I":
            btf, hft = dados["btf"], dados["hft"]
            bfb, hfb = dados["bfb"], dados["hfb"]
            hw  = h - hft - hfb
            x_v = -max(btf, bfb) / 2.0
            cota_h(-bfb / 2.0, bfb / 2.0, 0,             f"bfb={bfb:.0f}", y_bot)
            cota_h(-btf / 2.0, btf / 2.0, h,             f"btf={btf:.0f}", 10)
            cota_h(-bw  / 2.0, bw  / 2.0, hfb + hw / 2.0, f"bw={bw:.0f}",  -8)
            cota_v(0,      hfb,   x_v, f"hfb={hfb:.0f}", x_esq)
            cota_v(hfb,    h-hft, x_v, f"hw={hw:.0f}",   x_esq - 9)
            cota_v(h-hft,  h,     x_v, f"hft={hft:.0f}", x_esq)

        if lc and h_laje:
            cota_h(-lc / 2.0, lc / 2.0, h_tot, f"lc={lc:.0f}",   10)
            cota_v(h, h_tot,  -lc / 2.0,        f"hl={h_laje:.0f}", x_esq - 9)

    # ═════════════════════════════════════════════════════════════════════
    #  SEÇÃO 10 — Limites do campo de desenho (xlim / ylim)
    #
    #  [FIX-2] Os limites são calculados com base no conteúdo real:
    #    · Direita:  texto das anotações d' e d
    #    · Esquerda: texto das cotações verticais (mais afastadas para I/T)
    #    · Topo:     cotações horizontais superiores
    #    · Base:     cotações horizontais inferiores
    #  Isso elimina as margens infladas que faziam a seção parecer pequena.
    # ═════════════════════════════════════════════════════════════════════

    # Conteúdo mais à DIREITA: texto da anotação d_util
    x_right_bound = x_du + 17.0

    # Conteúdo mais à ESQUERDA: texto das cotações verticais
    # cota_v coloca a seta em x = x_pos + xoff  e o texto em x - 1.8
    # Para Ret:   xoff_max = x_esq              → x = -meia_w + x_esq
    # Para T/I:   xoff_max = x_esq - 9          → x = -meia_w + x_esq - 9
    if tipo in ("T", "I"):
        x_left_bound = -meia_w + (x_esq - 9) - 2.5
    else:
        x_left_bound = -meia_w + x_esq - 2.5

    PAD = 3.0
    xlim_orig = (x_left_bound - PAD, x_right_bound + PAD)

    # Y: cotação inferior em y_bot=-10, cotação superior em h_tot+10
    ylim_orig = (y_bot - 4.0, h_tot + 15.0)

    ax.set_xlim(*xlim_orig)
    ax.set_ylim(*ylim_orig)
    ax.set_aspect("equal")
    ax.axis("off")

    # ═════════════════════════════════════════════════════════════════════
    #  SEÇÃO 11 — Painel de informações fixo (ax_panel)
    #
    #  ax_panel é independente de ax → não sofre zoom/pan.
    # ═════════════════════════════════════════════════════════════════════
    laje_str = f" + Laje {h_laje:.0f} cm" if h_laje else ""
    titulo   = f"Seção {tipo}{laje_str}"

    ax_panel.text(0.50, 0.97, "DETALHAMENTO",
                  color=_C["texto"], fontsize=9.5, fontweight="bold",
                  ha="center", va="top", transform=ax_panel.transAxes,
                  fontfamily="monospace")
    ax_panel.text(0.50, 0.92, titulo,
                  color=_C["accent"], fontsize=8.5,
                  ha="center", va="top", transform=ax_panel.transAxes,
                  fontfamily="monospace")
    ax_panel.axhline(0.895, color=_C["painel_b"], lw=0.8, xmin=0.05, xmax=0.95)

    ax_panel.text(0.50, 0.865,
                  "🖱 Scroll: zoom  |  MMB+drag: pan  |  2×click: reset",
                  color="#666666", fontsize=6.2, ha="center", va="top",
                  transform=ax_panel.transAxes, fontfamily="monospace",
                  style="italic")
    ax_panel.axhline(0.850, color=_C["painel_b"], lw=0.5, xmin=0.05, xmax=0.95)

    y_cur = 0.825

    # ── Bloco: Armadura Inferior ──────────────────────────────────────────
    if pos_inf and as_inf:
        n_real = len(pos_inf)
        ax_panel.add_patch(mpatches.FancyBboxPatch(
            (0.04, y_cur - 0.095), 0.92, 0.085,
            boxstyle="round,pad=0.01",
            facecolor="#2A1A1A", edgecolor=_C["inf"],
            lw=0.8, transform=ax_panel.transAxes, zorder=2,
        ))
        ax_panel.text(0.08, y_cur - 0.010, "▶ ARM. INFERIOR",
                      color=_C["inf"], fontsize=7.8, fontweight="bold", va="top",
                      transform=ax_panel.transAxes, fontfamily="monospace")
        ax_panel.text(0.08, y_cur - 0.042,
                      f"  {n_real}φ{as_inf['diametro']:.0f}mm"
                      f"   As = {area_inf:.2f} cm²",
                      color=_C["texto"], fontsize=7.2, va="top",
                      transform=ax_panel.transAxes, fontfamily="monospace")
        ax_panel.text(0.08, y_cur - 0.072,
                      f"  d'ᵢ = {d_prime_inf:.2f} cm"
                      f"   d = {d_util:.2f} cm",
                      color=_C["texto"], fontsize=7.2, va="top",
                      transform=ax_panel.transAxes, fontfamily="monospace")
        y_cur -= 0.115

    # ── Bloco: Armadura Superior ──────────────────────────────────────────
    if pos_sup and as_sup:
        n_real = len(pos_sup)
        ax_panel.add_patch(mpatches.FancyBboxPatch(
            (0.04, y_cur - 0.095), 0.92, 0.085,
            boxstyle="round,pad=0.01",
            facecolor="#0F1A2A", edgecolor=_C["sup"],
            lw=0.8, transform=ax_panel.transAxes, zorder=2,
        ))
        ax_panel.text(0.08, y_cur - 0.010, "▶ ARM. SUPERIOR",
                      color=_C["sup"], fontsize=7.8, fontweight="bold", va="top",
                      transform=ax_panel.transAxes, fontfamily="monospace")
        ax_panel.text(0.08, y_cur - 0.042,
                      f"  {n_real}φ{as_sup['diametro']:.0f}mm"
                      f"   As = {area_sup:.2f} cm²",
                      color=_C["texto"], fontsize=7.2, va="top",
                      transform=ax_panel.transAxes, fontfamily="monospace")
        ax_panel.text(0.08, y_cur - 0.072,
                      f"  d'ₛ = {d_prime_sup:.2f} cm",
                      color=_C["texto"], fontsize=7.2, va="top",
                      transform=ax_panel.transAxes, fontfamily="monospace")
        y_cur -= 0.115

    # ── Bloco: Estribo ────────────────────────────────────────────────────
    ax_panel.add_patch(mpatches.FancyBboxPatch(
        (0.04, y_cur - 0.085), 0.92, 0.075,
        boxstyle="round,pad=0.01",
        facecolor="#1E1610", edgecolor=_C["estribo"],
        lw=0.8, transform=ax_panel.transAxes, zorder=2,
    ))
    ax_panel.text(0.08, y_cur - 0.010, "▶ ESTRIBO",
                  color=_C["estribo"], fontsize=7.8, fontweight="bold", va="top",
                  transform=ax_panel.transAxes, fontfamily="monospace")
    ax_panel.text(0.08, y_cur - 0.040,
                  f"  φ{phi_estribo:.0f}mm   c = {c:.0f} cm"
                  f"   lh = {lh:.1f} cm",
                  color=_C["texto"], fontsize=7.2, va="top",
                  transform=ax_panel.transAxes, fontfamily="monospace")
    ax_panel.text(0.08, y_cur - 0.065,
                  f"  r_int = {2 * phi_est:.2f} cm",
                  color=_C["texto"], fontsize=7.2, va="top",
                  transform=ax_panel.transAxes, fontfamily="monospace")
    y_cur -= 0.105

    ax_panel.axhline(y_cur + 0.01, color=_C["painel_b"], lw=0.6,
                     xmin=0.05, xmax=0.95)
    y_cur -= 0.025

    # ── Propriedades da seção ─────────────────────────────────────────────
    ax_panel.text(0.08, y_cur, "PROPRIEDADES DA SEÇÃO",
                  color=_C["accent"], fontsize=7.0, fontweight="bold", va="top",
                  transform=ax_panel.transAxes, fontfamily="monospace")
    y_cur -= 0.030

    props = [
        f"bw = {bw:.0f} cm",
        f"h  = {h:.0f} cm" + (f"  (+{h_laje:.0f} cm laje)" if h_laje else ""),
    ]
    if tipo == "T":
        props += [f"bf = {dados['bf']:.0f} cm", f"hf = {dados['hf']:.0f} cm"]
    elif tipo == "I":
        props += [f"btf={dados['btf']:.0f}  hft={dados['hft']:.0f} cm",
                  f"bfb={dados['bfb']:.0f}  hfb={dados['hfb']:.0f} cm"]
    if lc and h_laje:
        props.append(f"lc = {lc:.0f} cm")

    for linha in props:
        ax_panel.text(0.10, y_cur, f"  {linha}",
                      color=_C["texto"], fontsize=7.0, va="top",
                      transform=ax_panel.transAxes, fontfamily="monospace")
        y_cur -= 0.028

    ax_panel.axhline(y_cur + 0.015, color=_C["painel_b"], lw=0.6,
                     xmin=0.05, xmax=0.95)
    y_cur -= 0.025

    # ── Parâmetros de espaçamento ─────────────────────────────────────────
    ax_panel.text(0.08, y_cur, "PARÂMETROS",
                  color=_C["accent"], fontsize=7.0, fontweight="bold", va="top",
                  transform=ax_panel.transAxes, fontfamily="monospace")
    y_cur -= 0.028

    for linha in [
        f"ah_inf = {ah_min_inf:.0f} cm  |  av_inf = {av_inf:.0f} cm",
        f"ah_sup = {ah_min_sup:.0f} cm  |  av_sup = {av_sup:.0f} cm",
        f"folga vibrador = {folga_vibrador:.0f} cm",
    ]:
        ax_panel.text(0.10, y_cur, f"  {linha}",
                      color=_C["texto"], fontsize=6.8, va="top",
                      transform=ax_panel.transAxes, fontfamily="monospace")
        y_cur -= 0.028

    # ── Legenda de cores (rodapé do painel) ───────────────────────────────
    ax_panel.axhline(0.06, color=_C["painel_b"], lw=0.6, xmin=0.05, xmax=0.95)
    leg_elems = []
    if pos_inf:
        leg_elems.append(Line2D([0], [0], marker="o", color="none",
                                markerfacecolor=_C["inf"], markeredgecolor="white",
                                markersize=8, markeredgewidth=0.4,
                                label="Arm. inferior"))
    if pos_sup:
        leg_elems.append(Line2D([0], [0], marker="o", color="none",
                                markerfacecolor=_C["sup"], markeredgecolor="white",
                                markersize=8, markeredgewidth=0.4,
                                label="Arm. superior"))
    leg_elems.append(Line2D([0], [0], color=_C["estribo"], lw=3,
                            label="Estribo"))

    leg = ax_panel.legend(
        handles=leg_elems,
        loc="lower center",
        bbox_to_anchor=(0.50, 0.00),
        facecolor=_C["painel"], edgecolor=_C["painel_b"],
        labelcolor=_C["texto"], fontsize=7.0,
        handlelength=1.5, framealpha=0.95, ncol=1,
    )
    leg.get_title().set_color(_C["texto"])

    for spine in ax_panel.spines.values():
        spine.set_edgecolor(_C["painel_b"])
        spine.set_linewidth(0.8)
        spine.set_visible(True)

    # ── Título da figura ──────────────────────────────────────────────────
    fig.text(
        0.32, 0.975,
        f"Detalhamento Estrutural — NBR 6118  |  Seção {tipo}{laje_str}",
        color=_C["texto"], fontsize=9.0, fontweight="bold",
        ha="center", va="top", fontfamily="monospace",
        transform=fig.transFigure,
    )

    # ═════════════════════════════════════════════════════════════════════
    #  SEÇÃO 12 — setup_zoom_pan: zoom/pan estilo AutoCAD em ax
    #
    #  · Scroll ↑/↓         → zoom in/out centrado no cursor (apenas ax)
    #  · MMB + arrastar     → pan contínuo (apenas ax)
    #  · Duplo-clique       → restaura xlim/ylim originais (apenas ax)
    #
    #  ax_panel NÃO é afetado — suas transformações (transAxes) são imutáveis.
    # ═════════════════════════════════════════════════════════════════════

    def setup_zoom_pan(canvas) -> None:
        """
        Conecta callbacks de zoom/pan ao canvas Qt.

        Deve ser chamado **após** ``FigureCanvas(fig)`` ser instanciado no
        módulo de lógica para garantir que os eventos sejam registrados no
        canvas correto.

        Parâmetros
        ----------
        canvas : FigureCanvasQTAgg
            Canvas Qt retornado por ``FigureCanvas(fig)``.
        """
        _pan: dict = {
            "ativo": False,
            "x0":    0.0,
            "y0":    0.0,
            "xlim0": xlim_orig,
            "ylim0": ylim_orig,
        }

        def on_scroll(event):
            """Zoom incremental centrado na posição do cursor."""
            if event.inaxes is not ax:
                return
            xc = float(event.xdata) if event.xdata is not None else sum(ax.get_xlim()) / 2.0
            yc = float(event.ydata) if event.ydata is not None else sum(ax.get_ylim()) / 2.0
            fator = 0.80 if event.button == "up" else 1.25
            x_lo, x_hi = ax.get_xlim()
            y_lo, y_hi = ax.get_ylim()
            ax.set_xlim(xc - (xc - x_lo) * fator, xc + (x_hi - xc) * fator)
            ax.set_ylim(yc - (yc - y_lo) * fator, yc + (y_hi - yc) * fator)
            canvas.draw_idle()

        def on_press(event):
            """Inicia o pan ao pressionar MMB (button == 2)."""
            if event.inaxes is not ax or event.button != 2:
                return
            _pan["ativo"] = True
            _pan["x0"]    = event.xdata if event.xdata is not None else 0.0
            _pan["y0"]    = event.ydata if event.ydata is not None else 0.0
            _pan["xlim0"] = ax.get_xlim()
            _pan["ylim0"] = ax.get_ylim()

        def on_motion(event):
            """Pan enquanto MMB está pressionado."""
            if not _pan["ativo"] or event.inaxes is not ax:
                return
            if event.xdata is None or event.ydata is None:
                return
            dx = event.xdata - _pan["x0"]
            dy = event.ydata - _pan["y0"]
            x_lo, x_hi = _pan["xlim0"]
            y_lo, y_hi = _pan["ylim0"]
            ax.set_xlim(x_lo - dx, x_hi - dx)
            ax.set_ylim(y_lo - dy, y_hi - dy)
            canvas.draw_idle()

        def on_release(event):
            """Encerra o pan ao soltar MMB."""
            if event.button == 2:
                _pan["ativo"] = False

        def on_dblclick(event):
            """Restaura visão original ao duplo-clique sobre ax."""
            if event.inaxes is ax and event.dblclick:
                ax.set_xlim(*xlim_orig)
                ax.set_ylim(*ylim_orig)
                canvas.draw_idle()

        canvas.mpl_connect("scroll_event",         on_scroll)
        canvas.mpl_connect("button_press_event",   on_press)
        canvas.mpl_connect("motion_notify_event",  on_motion)
        canvas.mpl_connect("button_release_event", on_release)
        canvas.mpl_connect("button_press_event",   on_dblclick)

    return fig, d_prime_inf, d_prime_sup, setup_zoom_pan


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  BLOCO 6 — Entrypoint de teste                                           ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    import io
    from PIL import Image
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    # ── Parâmetros globais dos testes ──────────────────────────────────────
    PHI_EST    = 10.0    # diâmetro do estribo (mm)
    COB        = 3.0     # cobrimento (cm)
    AH_MIN     = 2.0     # espaçamento h mínimo (cm)
    AV         = 2.0     # espaçamento v mínimo (cm)
    FOLGA_VIB  = 6.0     # folga do vibrador (cm)
    DPI        = 100

    casos = [
        # ── Caso 1: Retangular, 1ª camada exata, sem laje ─────────────────
        dict(label="1 – Retangular  6φ20  (1 camada exata)",
             dados={"Tipo": "Retangular", "bw": 30.0, "h": 65.0},
             as_inf={"n": 6,  "diametro": 20.0},
             as_sup={"n": 2,  "diametro": 10.0},
             h_laje=None, lc=None),

        # ── Caso 2: Retangular, 3 barras residuais (verifica simetria) ────
        dict(label="2 – Retangular  7φ20  (3 barras na 2ª camada – simetria)",
             dados={"Tipo": "Retangular", "bw": 30.0, "h": 65.0},
             as_inf={"n": 7,  "diametro": 20.0},
             as_sup={"n": 3,  "diametro": 16.0},
             h_laje=None, lc=None),

        # ── Caso 3: T com laje, muitas barras ─────────────────────────────
        dict(label="3 – T  14φ25  com laje (folga vibrador inf+sup)",
             dados={"Tipo": "T", "bw": 25.0, "h": 100.0,
                    "bf": 65.0, "hf": 20.0},
             as_inf={"n": 14, "diametro": 25.0},
             as_sup={"n": 8,  "diametro": 16.0},
             h_laje=20.0, lc=150.0),

        # ── Caso 4: I com laje, 22 barras inferiores ──────────────────────
        dict(label="4 – I  22φ25  com laje (múltiplas camadas simétricas)",
             dados={"Tipo": "I", "bw": 25.0, "h": 150.0,
                    "btf": 50.0, "hft": 20.0,
                    "bfb": 60.0, "hfb": 25.0},
             as_inf={"n": 22, "diametro": 25.0},
             as_sup={"n": 8,  "diametro": 20.0},
             h_laje=20.0, lc=200.0),
    ]

    imgs: list[np.ndarray] = []

    for caso in casos:
        print(f"\n{'─'*65}\n  {caso['label']}\n{'─'*65}")

        fig, dp_inf, dp_sup, _setup = desenhar_detalhamento(
            dados=caso["dados"],
            as_inf=caso["as_inf"],
            as_sup=caso["as_sup"],
            c=COB,
            phi_estribo=PHI_EST,
            ah_min_inf=AH_MIN,
            ah_min_sup=AH_MIN,
            av_inf=AV,
            av_sup=AV,
            folga_vibrador=FOLGA_VIB,
            h_laje=caso["h_laje"],
            largura_colaborante=caso["lc"],
            exibir_cotas=True,
            dpi=DPI,
            tamanho_fixo_qframe=True,
        )

        FigureCanvasAgg(fig)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=DPI,
                    facecolor=fig.get_facecolor())
        buf.seek(0)
        imgs.append(
            np.array(Image.open(buf).convert("RGB").resize((951, 551),
                                                            Image.LANCZOS))
        )
        print(f"  d'inf = {dp_inf:.2f} cm  |  d'sup = {dp_sup:.2f} cm")
        plt.close("all")

    # Salva painel 2×2
    if len(imgs) >= 4:
        row1 = np.concatenate(imgs[:2], axis=1)
        row2 = np.concatenate(imgs[2:4], axis=1)
        painel = np.concatenate([row1, row2], axis=0)
        saida = "/tmp/detalhe_teste_v4.png"
        Image.fromarray(painel).save(saida)
        print(f"\n  Painel 2×2 salvo em {saida}")
    elif len(imgs) >= 2:
        painel = np.concatenate(imgs[:2], axis=1)
        saida = "/tmp/detalhe_teste_v4.png"
        Image.fromarray(painel).save(saida)
        print(f"\n  Painel 1×2 salvo em {saida}")
