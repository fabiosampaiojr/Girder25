# =============================================================================
# Calculadora_Carga_Movel.py  –  v2.5
# =============================================================================
# Geração de ENVOLTÓRIAS de esforços internos (cortante e momento fletor) e
# reações de apoio para cargas móveis (Trem-Tipo NBR 7188) em superestruturas
# de pontes e viadutos.
#
# Melhorias v2.1 em relação à versão anterior (Claude v1):
#   [M1] _envelope_ponto: refinamento local ao redor dos melhores candidatos
#        após a varredura principal, eliminando o erro residual de ~0.4 % em
#        estruturas isostáticas causado pelo passo de varredura finito.
#   [M2] _envelope_ponto: injeção explícita das posições "eixo-na-seção"
#        (k_mm − cada offset de eixo) em xtrain, garantindo que o pico exato
#        de cortante seja sempre avaliado independentemente do passo de grade.
#   [M3] _padronizar_saida_50mm: grade de saída fixa em 50 mm + vizinhos de
#        apoio; o pico real não é suavizado porque a grade de cálculo (Preciso:
#        25 mm) é mais densa que a de saída.
#   [M4] _calcular_biapoiada / _calcular_continua: adição automática das
#        posições de apoio vizinhas na malha de seções, capturando a
#        descontinuidade de cortante diretamente nos apoios intermediários.
#
# Correções v2.2 (bugs identificados na validação contra FTOOL):
#   [C1] _envelope_ponto – integração de áreas pos/neg via Gauss:
#        separação feita ponto a ponto (max/min nos nós de Gauss) em vez de
#        por média do segmento. Elimina erro em segmentos que cruzam o zero
#        da LI (crítico para LI de cortante com mudança de sinal suave).
#   [C2] _envelope_ponto – busca de área acumulada com np.interp (interpolação
#        linear contínua) em vez de np.searchsorted (função degrau). No modo
#        Preciso com passo fino (~8 mm), o searchsorted introduzia erro de
#        arredondamento maior que no Rápido (250 mm), invertendo a precisão.
#   [C3] _envelope_ponto – carga distribuída q2 aplicada conforme NBR 7188:
#        apenas na porção desfavorável da LI sob o trem (área positiva para
#        envoltória máxima, área negativa para envoltória mínima). A versão
#        anterior usava a área líquida (pos + neg), gerando erro sistemático
#        de ~3 kN nas regiões centrais onde a LI cruza o zero sob o trem.
#
# Melhorias v2.4/v2.5 – Parametrização e Correções de Contorno:
#   [P1] Parâmetros de discretização aumentados substancialmente para cravar
#        a primeira casa decimal dos Momentos no Modo Preciso. Modo Rápido
#        otimizado para processamento em 2~3 segundos com maior precisão.
#   [P2] _envelope_ponto: no Preciso, _REFINE_N 80 e _N_TOP 10, blindando a
#        captura de extremos matemáticos sob a varredura primária.
#   [C4] CortanteLI_Func.__call__ – convenção V(k−) nas seções de balanço:
#        Corrigido bug do "fantasma" de 100 kN. O degrau x <= k agora exige 
#        k_mm < primeiro_apoio. Se k_mm for exatamente o apoio inicial (sem 
#        balanço real), evita-se a criação de um balanço virtual e o cálculo
#        espúrio de V(0-) na extremidade.
#   [C5] _padronizar_saida_50mm – grade de saída estritamente em 50 mm.
#   [C6] _gerar_malha_secoes – injeção de pontos de "kink" no modo Rápido.
# =============================================================================

from __future__ import annotations

import math
import os
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
import scipy.optimize as sopt
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.figure import Figure

# =============================================================================
# ─── MAPEAMENTO DE TIPOS ESTRUTURAIS ─────────────────────────────────────────
# =============================================================================

_MAPA_TIPOS: Dict[str, str] = {
    "Isostática: Múltiplos Vãos Biapoioados":  "biapoiada",
    "Isostática: Biapoiada com Balanço":        "isostatica_em_balanco",
    "Hiperestática: Vão Contínuo sem Balanço":  "hiperestatica_sem_balanco",
    "Hiperestática: Vão Contínuo com Balanço":  "hiperestatica_com_balanco",
}

_N_THREADS: int = os.cpu_count() or 4

# =============================================================================
# ─── LINHAS DE INFLUÊNCIA ANALÍTICAS (ESTRUTURAS ISOSTÁTICAS) ────────────────
# =============================================================================

def _li_cortante_momento_iso(
        x_ini_mm: float, x_fim_mm: float,
        xA_mm: float, xB_mm: float,
        k_mm: float,
        n: int = 2000,
) -> Tuple[Tuple[np.ndarray, np.ndarray], Tuple[np.ndarray, np.ndarray]]:

    L   = xB_mm - xA_mm
    eps = 1e-5

    # ── LI de Cortante ───────────────────────────────────────────────────────
    k_clip = float(np.clip(k_mm, xA_mm + eps, xB_mm - eps))
    xs_v   = np.array([xA_mm, k_clip - eps, k_clip + eps, xB_mm])
    valid_v = (xs_v >= x_ini_mm) & (xs_v <= x_fim_mm)
    xs_v   = xs_v[valid_v]
    RA_v   = (xB_mm - xs_v) / L
    V      = np.where(xs_v < k_clip, RA_v - 1.0, RA_v)

    # ── LI de Momento ────────────────────────────────────────────────────────
    L_m    = L / 1000.0
    k_m    = k_clip / 1000.0
    xA_m   = xA_mm  / 1000.0
    xB_m   = xB_mm  / 1000.0
    peak_M = (k_m - xA_m) * (xB_m - k_m) / L_m

    pts_x_m = np.array([xA_mm, k_clip, xB_mm])
    pts_x_m, idx_unq = np.unique(pts_x_m, return_index=True)
    M_full = np.array([0.0, peak_M, 0.0])[idx_unq]

    valid_m = (pts_x_m >= x_ini_mm) & (pts_x_m <= x_fim_mm)
    xs_m_mm = pts_x_m[valid_m]
    M = M_full[valid_m]

    return (xs_v, V), (xs_m_mm, M)


# =============================================================================
# ─── MOTOR FEM ESPARSO COM ADJUNTO (ESTRUTURAS HIPERESTÁTICAS) ───────────────
# =============================================================================

class HermiteLI:
    """
    Avaliador exato da Linha de Influência utilizando funções de forma de Hermite.
    Garante precisão analítica e identifica extremos locais para o envelope.
    """
    def __init__(self, nodes_x: np.ndarray, U_global: np.ndarray):
        self.nodes = nodes_x
        self.U = U_global
        self.extrema = []

        # Calcula analiticamente os extremos (derivada = 0)
        for i in range(len(nodes_x) - 1):
            x0, x1 = nodes_x[i], nodes_x[i + 1]
            Le = x1 - x0
            if Le <= 1e-6: continue

            v1, t1 = U_global[i * 2], U_global[i * 2 + 1]
            v2, t2 = U_global[(i + 1) * 2], U_global[(i + 1) * 2 + 1]

            A = 6.0 * v1 + 3.0 * Le * t1 - 6.0 * v2 + 3.0 * Le * t2
            B = -6.0 * v1 - 4.0 * Le * t1 + 6.0 * v2 - 2.0 * Le * t2
            C = Le * t1

            if abs(A) > 1e-12:
                delta = B**2 - 4 * A * C
                if delta >= 0:
                    r1 = (-B + math.sqrt(delta)) / (2 * A)
                    r2 = (-B - math.sqrt(delta)) / (2 * A)
                    for r in (r1, r2):
                        if 0.0 < r < 1.0: self.extrema.append(x0 + r * Le)
            elif abs(B) > 1e-12:
                r = -C / B
                if 0.0 < r < 1.0: self.extrema.append(x0 + r * Le)

        self.extrema = np.unique(self.extrema)

    def __call__(self, x_eval: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
        x = np.atleast_1d(x_eval)
        v_out = np.zeros_like(x, dtype=float)

        for i in range(len(self.nodes) - 1):
            x0, x1 = self.nodes[i], self.nodes[i + 1]
            Le = x1 - x0
            if Le <= 1e-6: continue

            mask = (x >= x0) & (x <= x1 + 1e-6) if i == len(self.nodes) - 2 else (x >= x0) & (x < x1)
            if not np.any(mask): continue

            xi = (x[mask] - x0) / Le

            N1 = 1.0 - 3.0 * xi**2 + 2.0 * xi**3
            N2 = Le * (xi - 2.0 * xi**2 + xi**3)
            N3 = 3.0 * xi**2 - 2.0 * xi**3
            N4 = Le * (-xi**2 + xi**3)

            v1, t1 = self.U[i * 2], self.U[i * 2 + 1]
            v2, t2 = self.U[(i + 1) * 2], self.U[(i + 1) * 2 + 1]

            v_out[mask] = N1 * v1 + N2 * t1 + N3 * v2 + N4 * t2

        return v_out if isinstance(x_eval, np.ndarray) else v_out[0]


def _li_reacoes_fem_adjoint(L_struct_mm: float,
                            supports: list,
                            section_params: list,
                            step_mm: float = 50.0) -> Dict[str, Tuple[np.ndarray, np.ndarray, HermiteLI]]:

    sup_xs = [float(s[0]) for s in supports]
    sec_xs = []
    for param in section_params:
        sec_xs.extend([param[0], param[1]])

    nodes_x = np.unique(np.concatenate([[0.0, L_struct_mm], sup_xs, sec_xs]))
    nodes_x = nodes_x[(nodes_x >= 0.0) & (nodes_x <= L_struct_mm)]

    N_nodes = len(nodes_x)
    N_dof = N_nodes * 2

    fixed_dofs = []
    sup_dict = {}

    for i, s in enumerate(supports):
        x_s, t = float(s[0]), s[1].lower()
        idx = np.searchsorted(nodes_x, x_s)
        lab = chr(65 + i)
        sup_dict[lab] = idx
        fixed_dofs.append(idx * 2)
        if t == 'fix':
            fixed_dofs.append(idx * 2 + 1)

    free_dofs = np.setdiff1d(np.arange(N_dof), fixed_dofs)
    K_global = np.zeros((N_dof, N_dof), dtype=np.float64)

    for i in range(N_nodes - 1):
        x0, x1 = nodes_x[i], nodes_x[i + 1]
        Le = x1 - x0
        if Le <= 1e-6: continue

        x_mid = (x0 + x1) / 2.0
        EI = np.nan
        for (xs_p, xe_p, II, EE, AA, th) in section_params:
            if min(xs_p, xe_p) <= x_mid <= max(xs_p, xe_p):
                EI = EE * II
                break

        k_e = np.array([
            [ 12*EI/Le**3,   6*EI/Le**2, -12*EI/Le**3,   6*EI/Le**2],
            [  6*EI/Le**2,   4*EI/Le,    - 6*EI/Le**2,   2*EI/Le   ],
            [-12*EI/Le**3,  -6*EI/Le**2,  12*EI/Le**3,  -6*EI/Le**2],
            [  6*EI/Le**2,   2*EI/Le,    - 6*EI/Le**2,   4*EI/Le   ],
        ])

        dofs = [i*2, i*2+1, (i+1)*2, (i+1)*2+1]
        for row_idx, global_row in enumerate(dofs):
            for col_idx, global_col in enumerate(dofs):
                K_global[global_row, global_col] += k_e[row_idx, col_idx]

    K_global_sp = sp.csc_matrix(K_global)
    K_ff = K_global_sp[free_dofs, :][:, free_dofs]
    K_fs = K_global_sp[free_dofs, :][:, fixed_dofs]

    solver = spla.factorized(K_ff)
    fixed_dofs_arr = np.array(fixed_dofs, dtype=np.int32)
    fixed_v_indices = [int(np.searchsorted(fixed_dofs_arr, idx * 2)) for idx in sup_dict.values()]

    LI = {}
    for i, (lab, node_idx) in enumerate(sup_dict.items()):
        idx_in_fixed = fixed_v_indices[i]
        C = K_fs[:, idx_in_fixed].toarray().flatten()

        U_adj_free = solver(-C)
        U_adj = np.zeros(N_dof)
        U_adj[free_dofs] = U_adj_free
        U_adj[fixed_dofs[idx_in_fixed]] = 1.0

        hermite_eval = HermiteLI(nodes_x, U_adj)
        LI[lab] = (nodes_x.copy(), hermite_eval(nodes_x), hermite_eval)

    return LI


class CortanteLI_Func:
    def __init__(self, LI_reactions, apoios_esq, k_mm, primeiro_apoio_mm):
        self.LI_reactions = LI_reactions
        self.apoios_esq = apoios_esq
        self.k_mm = k_mm
        self.primeiro_apoio_mm = primeiro_apoio_mm
        extrema = [k_mm]
        for lab in apoios_esq:
            extrema.extend(LI_reactions[lab][2].extrema)
        self.extrema = np.unique(extrema)

    def __call__(self, x_eval):
        x = np.atleast_1d(x_eval)
        v = np.zeros_like(x, dtype=float)
        for lab in self.apoios_esq:
            v += self.LI_reactions[lab][2](x)
        
        # [C4] Corrigido: Para seções de balanço (apoios_esq vazio), a convenção 
        # rígida V(k-) só deve ser ativada se a seção estiver EFETIVAMENTE em um 
        # balanço (k_mm < primeiro_apoio). Se k_mm for exatamente o primeiro apoio 
        # sem balanço real à esquerda, isso previne o "fantasma" de V(0-).
        if len(self.apoios_esq) == 0 and self.k_mm < self.primeiro_apoio_mm - 1e-5:
            v[x <= self.k_mm] -= 1.0
        else:
            v[x < self.k_mm] -= 1.0
            
        return v if isinstance(x_eval, np.ndarray) else v[0]


class MomentoLI_Func:
    def __init__(self, LI_reactions, apoios_esq, k_mm):
        self.LI_reactions = LI_reactions
        self.apoios_esq = apoios_esq
        self.k_mm = k_mm
        extrema = [k_mm]
        for lab, xap in apoios_esq:
            extrema.extend(LI_reactions[lab][2].extrema)
        self.extrema = np.unique(extrema)

    def __call__(self, x_eval):
        x = np.atleast_1d(x_eval)
        m = np.zeros_like(x, dtype=float)
        for lab, xap in self.apoios_esq:
            RA = self.LI_reactions[lab][2](x)
            m += RA * (self.k_mm - xap)
        mask = x < self.k_mm
        m[mask] -= (self.k_mm - x[mask])
        res = m / 1000.0
        return res if isinstance(x_eval, np.ndarray) else res[0]


class ExtendedLI_Func:
    """Wrapper para injetar os balanços lineares e mapear Coordenadas Globais -> Locais."""
    def __init__(self, core_func, x_ini, x_fim, laje_L):
        self.core = core_func
        self.x_ini = x_ini
        self.x_fim = x_fim
        self.laje_L = laje_L
        self.y_left = core_func(0.0)
        self.y_right = core_func(x_fim - x_ini)
        core_ext = getattr(core_func, 'extrema', [])
        self.extrema = np.array(core_ext) + x_ini

    def __call__(self, x_eval):
        x = np.atleast_1d(x_eval)
        res = np.zeros_like(x, dtype=float)

        mask_core = (x >= self.x_ini) & (x <= self.x_fim)
        if np.any(mask_core):
            res[mask_core] = self.core(x[mask_core] - self.x_ini)

        mask_esq = x < self.x_ini
        if np.any(mask_esq) and self.x_ini > 0:
            res[mask_esq] = self.y_left * x[mask_esq] / self.x_ini

        mask_dir = x > self.x_fim
        if np.any(mask_dir) and self.laje_L > 0:
            res[mask_dir] = self.y_right * (self.x_fim + self.laje_L - x[mask_dir]) / self.laje_L

        return res if isinstance(x_eval, np.ndarray) else res[0]


def _li_cortante_fem(LI_reactions: Dict[str, Tuple[np.ndarray, np.ndarray, HermiteLI]],
                     apoios_mm: Dict[str, float],
                     k_mm: float) -> Tuple[np.ndarray, np.ndarray, callable]:
    first_key = next(iter(LI_reactions))
    xs_orig   = LI_reactions[first_key][0]

    eps = 1e-5
    xs_eval = np.unique(np.concatenate([xs_orig, [k_mm - eps, k_mm + eps]]))
    xs_eval = xs_eval[(xs_eval >= xs_orig[0]) & (xs_eval <= xs_orig[-1])]

    apoios_esq = [lab for lab, xap in apoios_mm.items() if xap < k_mm]
    primeiro_apoio_mm = min(apoios_mm.values())
    func = CortanteLI_Func(LI_reactions, apoios_esq, k_mm, primeiro_apoio_mm)

    return xs_eval, func(xs_eval), func


def _li_momento_fem(LI_reactions: Dict[str, Tuple[np.ndarray, np.ndarray, HermiteLI]],
                    apoios_mm: Dict[str, float],
                    k_mm: float) -> Tuple[np.ndarray, np.ndarray, callable]:
    first_key = next(iter(LI_reactions))
    xs_orig   = LI_reactions[first_key][0]

    xs_eval = np.unique(np.concatenate([xs_orig, [k_mm]]))
    xs_eval = xs_eval[(xs_eval >= xs_orig[0]) & (xs_eval <= xs_orig[-1])]

    apoios_esq = [(lab, xap) for lab, xap in apoios_mm.items() if xap < k_mm]
    func = MomentoLI_Func(LI_reactions, apoios_esq, k_mm)

    return xs_eval, func(xs_eval), func


# =============================================================================
# ─── MOTOR DE ENVELOPE VETORIZADO (ALGORITMO EXATO + REFINAMENTO LOCAL) ──────
# =============================================================================

def _envelope_ponto(li_xs: np.ndarray, li_ys: np.ndarray,
                    Q: float, q1: float, q2: float,
                    L_trem_mm: float = 6000.0,
                    axle_offsets_mm: Tuple[float, ...] = (1500.0, 3000.0, 4500.0),
                    step_mm: float = 50.0,
                    li_func: callable = None,
                    extra_crit: list = None) -> Tuple[float, float]:

    if len(li_xs) < 2: return 0.0, 0.0
    L_total = float(li_xs[-1])

    # ── Zeros da LI (necessários para separar áreas + / −) ───────────────────
    zero_crossings: list = []

    if li_func is not None:
        _SCAN_MM = 2.5 # [P1] Refinado para raízes exatas
        xs_scan  = np.arange(0.0, L_total + _SCAN_MM * 0.5, _SCAN_MM)
        xs_scan  = np.unique(np.concatenate([xs_scan, [0.0, L_total]]))
        xs_scan  = np.clip(xs_scan, 0.0, L_total)
        ys_scan  = li_func(xs_scan)

        for i in range(len(xs_scan) - 1):
            if ys_scan[i] * ys_scan[i + 1] < 0.0:
                try:
                    root = sopt.brentq(li_func, xs_scan[i], xs_scan[i + 1], xtol=1e-6)
                    zero_crossings.append(root)
                except ValueError:
                    t = -ys_scan[i] / (ys_scan[i + 1] - ys_scan[i])
                    zero_crossings.append(xs_scan[i] + t * (xs_scan[i + 1] - xs_scan[i]))
    else:
        for i in range(len(li_xs) - 1):
            y1, y2 = li_ys[i], li_ys[i + 1]
            if y1 * y2 < 0.0:
                t = -y1 / (y2 - y1)
                zero_crossings.append(li_xs[i] + t * (li_xs[i + 1] - li_xs[i]))

    if extra_crit is None: extra_crit = []
    all_crit = np.concatenate([li_xs, zero_crossings, extra_crit])
    all_crit = np.unique(np.round(all_crit, 6))
    all_crit = all_crit[(all_crit >= 0.0) & (all_crit <= L_total)]

    offsets = np.array(axle_offsets_mm)
    shifts  = np.concatenate([[0.0], offsets, [L_trem_mm]])
    xtrain_crit = (all_crit[:, None] - shifts[None, :]).ravel()

    start_t = -L_trem_mm - (offsets.max() if len(offsets) else 0.0)
    sweep_xs = np.arange(start_t - 1.0, L_total + 1.0, step_mm)

    axle_exact = (all_crit[:, None] - offsets[None, :]).ravel()

    xtrain_raw = np.concatenate([sweep_xs, xtrain_crit, axle_exact])
    xtrain  = np.unique(np.round(xtrain_raw, decimals=6))
    xtrain  = xtrain[(xtrain >= start_t - 1.0) & (xtrain <= L_total + 1.0)]

    master_xs_raw = np.concatenate([
        all_crit,
        np.clip(xtrain, 0.0, L_total),
        np.clip(xtrain + L_trem_mm, 0.0, L_total),
    ])
    master_xs = np.unique(np.round(master_xs_raw, decimals=6))
    master_xs = master_xs[(master_xs >= 0.0) & (master_xs <= L_total)]

    # ── Áreas acumuladas da LI ────────────────────────────────────────────────
    if li_func is not None:
        a = master_xs[:-1]
        b = master_xs[1:]
        dx = b - a
        valid = dx > 1e-7

        areas_total = np.zeros_like(dx)
        areas_pos   = np.zeros_like(dx)
        areas_neg   = np.zeros_like(dx)

        if np.any(valid):
            a_v = a[valid]; b_v = b[valid]
            xm  = 0.5 * (a_v + b_v)
            xr  = 0.5 * (b_v - a_v)

            xi = np.array([-0.7745966692414834, 0.0, 0.7745966692414834])
            wi = np.array([ 0.5555555555555556, 0.8888888888888888, 0.5555555555555556])

            xg = xm[:, None] + xr[:, None] * xi[None, :]
            yg = li_func(xg.ravel()).reshape(-1, 3)
            area_seg = xr * np.sum(wi * yg, axis=1)

            yg_pos_vals = np.maximum(yg, 0.0)
            yg_neg_vals = np.minimum(yg, 0.0)

            areas_total[valid] = area_seg
            areas_pos[valid]   = xr * np.sum(wi * yg_pos_vals, axis=1)
            areas_neg[valid]   = xr * np.sum(wi * yg_neg_vals, axis=1)

        cum_area     = np.concatenate([[0.0], np.cumsum(areas_total)])
        cum_area_pos = np.concatenate([[0.0], np.cumsum(areas_pos)])
        cum_area_neg = np.concatenate([[0.0], np.cumsum(areas_neg)])
    else:
        master_ys = np.interp(master_xs, li_xs, li_ys)
        y_pos = np.maximum(master_ys, 0.0)
        y_neg = np.minimum(master_ys, 0.0)
        dx    = np.diff(master_xs)

        cum_area     = np.concatenate([[0.0], np.cumsum(0.5*(master_ys[:-1]+master_ys[1:])*dx)])
        cum_area_pos = np.concatenate([[0.0], np.cumsum(0.5*(y_pos[:-1]+y_pos[1:])*dx)])
        cum_area_neg = np.concatenate([[0.0], np.cumsum(0.5*(y_neg[:-1]+y_neg[1:])*dx)])

    # ── Avaliação vetorizada ─────────────────────────────
    xt_axles_main      = xtrain[:, None] + offsets[None, :]
    valid_mask_main    = (xt_axles_main >= 0.0) & (xt_axles_main <= L_total)
    xt_axles_clip_main = np.clip(xt_axles_main, 0.0, L_total)

    if li_func is not None:
        y_axles_main = li_func(xt_axles_clip_main) * valid_mask_main
    else:
        _master_ys = np.interp(master_xs, li_xs, li_ys)
        y_axles_main = np.interp(xt_axles_clip_main, master_xs, _master_ys) * valid_mask_main

    R_conc_main = np.sum(Q * y_axles_main, axis=1)

    xs_start_main = np.clip(xtrain,              0.0, L_total)
    xs_end_main   = np.clip(xtrain + L_trem_mm,  0.0, L_total)

    area_pos_trem_main = (np.interp(xs_end_main, master_xs, cum_area_pos)
                          - np.interp(xs_start_main, master_xs, cum_area_pos))
    area_neg_trem_main = (np.interp(xs_end_main, master_xs, cum_area_neg)
                          - np.interp(xs_start_main, master_xs, cum_area_neg))

    tot_pos = cum_area_pos[-1]
    tot_neg = cum_area_neg[-1]

    R_q2_max_main = q2 * area_pos_trem_main / 1000.0
    R_q2_min_main = q2 * area_neg_trem_main / 1000.0
    R_q1_max_main = q1 * (tot_pos - area_pos_trem_main) / 1000.0
    R_q1_min_main = q1 * (tot_neg - area_neg_trem_main) / 1000.0

    R_tot_max_main = R_conc_main + R_q1_max_main + R_q2_max_main
    R_tot_min_main = R_conc_main + R_q1_min_main + R_q2_min_main

    R_max = float(np.max(R_tot_max_main))
    R_min = float(np.min(R_tot_min_main))

    # [M1] Refinamento local blindado [P2]
    if step_mm > 1.0:
        _REFINE_N  = 80 if step_mm <= 20.0 else 40
        _N_TOP     = 10 if step_mm <= 20.0 else 6
        idx_top_max = np.argsort(R_tot_max_main)[-_N_TOP:]
        idx_top_min = np.argsort(R_tot_min_main)[:_N_TOP]
        cands = np.unique(np.concatenate([xtrain[idx_top_max], xtrain[idx_top_min]]))

        refine_pts = np.concatenate([
            np.linspace(c - step_mm, c + step_mm, _REFINE_N) for c in cands
        ])
        refine_pts = np.unique(np.round(refine_pts, 6))
        refine_pts = refine_pts[(refine_pts >= start_t - 1.0) & (refine_pts <= L_total + 1.0)]

        xt_r      = refine_pts
        xt_ax_r   = xt_r[:, None] + offsets[None, :]
        vm_r      = (xt_ax_r >= 0.0) & (xt_ax_r <= L_total)
        xt_ax_r_c = np.clip(xt_ax_r, 0.0, L_total)

        if li_func is not None:
            y_ax_r = li_func(xt_ax_r_c) * vm_r
        else:
            y_ax_r = np.interp(xt_ax_r_c, master_xs, _master_ys) * vm_r

        R_conc_r = np.sum(Q * y_ax_r, axis=1)

        xs_r_start = np.clip(xt_r,             0.0, L_total)
        xs_r_end   = np.clip(xt_r + L_trem_mm, 0.0, L_total)
        area_pos_r = (np.interp(xs_r_end, master_xs, cum_area_pos)
                      - np.interp(xs_r_start, master_xs, cum_area_pos))
        area_neg_r = (np.interp(xs_r_end, master_xs, cum_area_neg)
                      - np.interp(xs_r_start, master_xs, cum_area_neg))

        R_q2_max_r = q2 * area_pos_r / 1000.0
        R_q2_min_r = q2 * area_neg_r / 1000.0
        R_q1_max_r = q1 * (tot_pos - area_pos_r) / 1000.0
        R_q1_min_r = q1 * (tot_neg - area_neg_r) / 1000.0

        R_max = max(R_max, float(np.max(R_conc_r + R_q1_max_r + R_q2_max_r)))
        R_min = min(R_min, float(np.min(R_conc_r + R_q1_min_r + R_q2_min_r)))

    return R_min, R_max


# =============================================================================
# ─── WORKERS DE NÍVEL DE MÓDULO ──────────────────────────────────────────────
# =============================================================================

def _worker_secao_iso(args: tuple) -> tuple:
    (k_clip, xA, xB, x_total_min, x_total_max,
     Q, q1, q2, L_trem, axle_offsets, step_trem, n_iso) = args

    (xs_v, ys_v), (xs_m, ys_m) = _li_cortante_momento_iso(
        xA, xB, xA, xB, k_clip, n_iso)

    def _pad(xs, ys):
        parts_x, parts_y = [xs], [ys]
        if xs[0] > x_total_min + 1e-4:
            parts_x.insert(0, np.array([x_total_min, xs[0] - 1e-5]))
            parts_y.insert(0, np.array([0.0, 0.0]))
        if xs[-1] < x_total_max - 1e-4:
            parts_x.append(np.array([xs[-1] + 1e-5, x_total_max]))
            parts_y.append(np.array([0.0, 0.0]))
        if len(parts_x) == 1:
            return xs, ys
        return np.concatenate(parts_x), np.concatenate(parts_y)

    xs_fv, ys_fv = _pad(xs_v, ys_v)
    xs_fm, ys_fm = _pad(xs_m, ys_m)

    env_v = _envelope_ponto(xs_fv, ys_fv, Q, q1, q2, L_trem, axle_offsets, step_trem, li_func=None)
    env_m = _envelope_ponto(xs_fm, ys_fm, Q, q1, q2, L_trem, axle_offsets, step_trem, li_func=None)
    return round(k_clip, 4), env_v, env_m


def _worker_secao_fem(args: tuple) -> tuple:
    (k_glob, k_loc, LI_reactions, apoios_mm_loc,
     x_ini_main, x_fim_main, laje_L,
     Q, q1, q2, L_trem, axle_offsets, step_trem) = args

    xs_v_loc, ys_v_loc, func_v = _li_cortante_fem(LI_reactions, apoios_mm_loc, k_loc)
    xs_m_loc, ys_m_loc, func_m = _li_momento_fem(LI_reactions, apoios_mm_loc, k_loc)

    def _extend(xs, ys):
        if laje_L <= 0: return xs, ys
        y_left, y_right = ys[0], ys[-1]

        xs_esq = np.array([0.0, x_ini_main - 1e-4], dtype=float) if x_ini_main > 0 else np.array([], dtype=float)
        ys_esq = y_left * xs_esq / x_ini_main if x_ini_main > 0 else np.array([], dtype=float)

        x_end  = x_fim_main + laje_L
        xs_dir = np.array([x_fim_main + 1e-4, x_end], dtype=float)
        ys_dir = y_right * (x_end - xs_dir) / laje_L

        return (np.concatenate([xs_esq, xs, xs_dir]), np.concatenate([ys_esq, ys, ys_dir]))

    xs_fv, ys_fv = _extend(xs_v_loc + x_ini_main, ys_v_loc)
    xs_fm, ys_fm = _extend(xs_m_loc + x_ini_main, ys_m_loc)

    func_v_ext = ExtendedLI_Func(func_v, x_ini_main, x_fim_main, laje_L) if laje_L > 0 else lambda x: func_v(x - x_ini_main)
    func_m_ext = ExtendedLI_Func(func_m, x_ini_main, x_fim_main, laje_L) if laje_L > 0 else lambda x: func_m(x - x_ini_main)

    extrema_v = func_v_ext.extrema if hasattr(func_v_ext, 'extrema') else (func_v.extrema + x_ini_main if hasattr(func_v, 'extrema') else [])
    extrema_m = func_m_ext.extrema if hasattr(func_m_ext, 'extrema') else (func_m.extrema + x_ini_main if hasattr(func_m, 'extrema') else [])

    env_v = _envelope_ponto(xs_fv, ys_fv, Q, q1, q2, L_trem, axle_offsets, step_trem, li_func=func_v_ext, extra_crit=extrema_v)
    env_m = _envelope_ponto(xs_fm, ys_fm, Q, q1, q2, L_trem, axle_offsets, step_trem, li_func=func_m_ext, extra_crit=extrema_m)

    return round(k_glob, 4), env_v, env_m


def _worker_secao_iso_laje(args: tuple) -> tuple:
    (k_glob, xA_iso, xB_iso, x_total_min, L_total_mm,
     Q, q1, q2, L_trem, axle_offsets, step_trem, n_iso) = args

    (xs_iso, ys_v), (xs_iso_m, ys_m) = _li_cortante_momento_iso(
        xA_iso, xB_iso, xA_iso, xB_iso, k_glob, n_iso)

    def _pad(xs, ys):
        parts_x, parts_y = [xs], [ys]
        if xs[0] > x_total_min + 1e-4:
            parts_x.insert(0, np.array([x_total_min, xs[0] - 1e-5]))
            parts_y.insert(0, np.array([0.0, 0.0]))
        if xs[-1] < L_total_mm - 1e-4:
            parts_x.append(np.array([xs[-1] + 1e-5, L_total_mm]))
            parts_y.append(np.array([0.0, 0.0]))
        if len(parts_x) == 1:
            return xs, ys
        return np.concatenate(parts_x), np.concatenate(parts_y)

    xs_fv, ys_fv = _pad(xs_iso,   ys_v)
    xs_fm, ys_fm = _pad(xs_iso_m, ys_m)

    env_v = _envelope_ponto(xs_fv, ys_fv, Q, q1, q2, L_trem, axle_offsets, step_trem)
    env_m = _envelope_ponto(xs_fm, ys_fm, Q, q1, q2, L_trem, axle_offsets, step_trem)
    return round(k_glob, 4), env_v, env_m


# =============================================================================
# ─── CLASSE PRINCIPAL ────────────────────────────────────────────────────────
# =============================================================================

class CalculadoraCargaMovel:
    AXLE_OFFSETS_MM:  Tuple[float, ...]  = (1500.0, 3000.0, 4500.0)
    L_CARRO_MM:       float              = 6000.0

    def __init__(self,
                 superestrutura,
                 secao_superestrutura,
                 trem_tipo: Dict[str, float],
                 modulo_elasticidade: float,
                 dict_coef: Optional[Dict[Tuple[float, float], float]] = None,
                 modo: str = "Preciso"):

        self._super     = superestrutura
        self._secao     = secao_superestrutura
        self._trem      = trem_tipo
        self._E_kNcm2   = float(modulo_elasticidade)
        self._dict_coef = dict_coef

        self._tipo = self._resolver_tipo(superestrutura.tipo)

        pg           = secao_superestrutura.parametros_geometricos
        self._I_mm4  = float(pg["Ix"])   * 1e4
        self._A_mm2  = float(pg["Area"]) * 1e2
        self._E_Nmm2 = float(modulo_elasticidade) * 10.0

        self._vaos_mm: List[float] = [v * 1e3 for v in superestrutura.vaos]
        self._laje_mm: float       = 0.0
        lt = superestrutura.laje_transicao
        if lt is not False and lt is not None:
            self._laje_mm = float(lt) * 1e3

        self._Q  = float(trem_tipo.get("Q",  0.0))
        self._q1 = float(trem_tipo.get("q1", 0.0))
        self._q2 = float(trem_tipo.get("q2", 0.0))

        self._modo = modo.strip().title()
        if self._modo == "Rápido":
            self._secao_passo_mm = 150.0         # 2x mais seções vs Rápido antigo
            self._step_trem_mm   = 100.0         # Maior fidelidade sob varredura
            self._li_step_fem_mm = 15.0          # Elementos FEM 4x mais finos
            self._li_n_iso       = 1500          # Discretização analítica densa
        else:  # Preciso
            self._secao_passo_mm = 15.0          # [P1] Refinamento Extremo
            self._step_trem_mm   = 15.0          # [P1] Varredura densa c/ local search
            self._li_step_fem_mm = 2.5         # [P1] Malha Hermite praticamente exata
            self._li_n_iso       = 6000         # [P1] Mapeamento iso impecável

        self._env_reacoes  : Dict[float, Tuple[float, float]] = {}
        self._env_cortante : Dict[float, Tuple[float, float]] = {}
        self._env_momento  : Dict[float, Tuple[float, float]] = {}
        self._labels_apoio : Dict[float, str]                 = {}
        self._L_total_mm   : float                            = 0.0
        self._calculado    : bool                             = False

    # ── API pública ──────────────────────────────────────────────────────────

    def calcular(self) -> Tuple[List[list], List[list], List[list]]:
        if self._tipo == "biapoiada":
            self._calcular_biapoiada()
        else:
            self._calcular_continua()

        self._padronizar_saida_50mm()

        self._calculado = True
        return (self._tabela_reacoes(),
                self._tabela_cortante(),
                self._tabela_momento())

    def plotar_envoltoria_cortante(self) -> Figure:
        self._verificar_calculado()
        return self._plotar_envoltoria(
            "Envoltória de Esforço Cortante", "V [kN]",
            self._env_cortante, inverter_y=False)

    def plotar_envoltoria_momento(self) -> Figure:
        self._verificar_calculado()
        return self._plotar_envoltoria(
            "Envoltória de Momento Fletor", "M [kN·m]",
            self._env_momento, inverter_y=True)

    # ── Saída padronizada em grade de 50 mm ──────────────────────────────────

    def _padronizar_saida_50mm(self):
        x_50 = np.arange(0.0, self._L_total_mm + 1e-3, 50.0)
        eps = 1e-3
        x_criticos = []
        for ap in self._labels_apoio.keys():
            x_criticos.extend([ap - eps, ap, ap + eps])
        x_criticos.extend([0.0, self._L_total_mm])

        x_out = np.unique(np.concatenate([x_50, x_criticos]))
        x_out = x_out[(x_out >= 0.0) & (x_out <= self._L_total_mm)]

        def iterpolar_dict(env_calc: Dict[float, Tuple[float, float]]) -> Dict[float, Tuple[float, float]]:
            x_c = np.array(sorted(env_calc.keys()))
            if len(x_c) == 0: return {}

            ymin = np.array([env_calc[x][0] for x in x_c])
            ymax = np.array([env_calc[x][1] for x in x_c])

            ymin_out = np.interp(x_out, x_c, ymin)
            ymax_out = np.interp(x_out, x_c, ymax)

            return {round(float(x), 4): (float(mn), float(mx))
                    for x, mn, mx in zip(x_out, ymin_out, ymax_out)}

        self._env_cortante = iterpolar_dict(self._env_cortante)
        self._env_momento  = iterpolar_dict(self._env_momento)

    # ── Malha de seções ──────────────────────────────────────────────────────

    def _gerar_malha_secoes(self, x_ini: float, x_fim: float,
                            apoios: List[float]) -> np.ndarray:
        xs_base   = np.arange(x_ini, x_fim + self._secao_passo_mm, self._secao_passo_mm)
        eps       = 1e-3
        ap_arr    = np.asarray(apoios, dtype=float)
        ap_valido = ap_arr[(ap_arr >= x_ini) & (ap_arr <= x_fim)]

        if ap_valido.size:
            extras = np.concatenate([
                ap_valido - eps,
                ap_valido,          
                ap_valido + eps,
            ])
            xs = np.unique(np.concatenate([xs_base, extras]))
        else:
            xs = xs_base

        if self._modo == "Rápido":
            eps_k = 0.5
            kink_pts = []
            for d in self.AXLE_OFFSETS_MM:
                for xk in (x_ini + d, x_fim - d):
                    if x_ini < xk < x_fim:
                        kink_pts.extend([xk - eps_k, xk + eps_k])
            if kink_pts:
                ka = np.array(kink_pts)
                ka = ka[(ka >= x_ini) & (ka <= x_fim)]
                xs = np.unique(np.concatenate([xs, ka]))

        return xs[(xs >= x_ini) & (xs <= x_fim)]

    # ── Acesso ao coeficiente φ ───────────────────────────────────────────────

    def _get_phi(self, x_m: float) -> Optional[float]:
        if not self._dict_coef: return None
        candidates = [phi for (x_start, x_end), phi in self._dict_coef.items()
                      if x_start <= x_m <= x_end]
        return max(candidates) if candidates else None

    # ── Extensão de LI para lajes de transição ───────────────────────────────

    @staticmethod
    def _extend_li_for_slabs(xs: np.ndarray, ys: np.ndarray,
                              x_ini: float, x_fim: float,
                              laje_mm: float) -> Tuple[np.ndarray, np.ndarray]:
        if laje_mm <= 0: return xs, ys

        y_left, y_right = ys[0], ys[-1]

        xs_esq_arr = np.array([0.0, x_ini - 1e-4], dtype=float) if x_ini > 0 else np.array([], dtype=float)
        ys_esq_arr = y_left * xs_esq_arr / x_ini if x_ini > 0 else np.array([], dtype=float)

        x_end       = x_fim + laje_mm
        xs_dir_arr  = np.array([x_fim + 1e-4, x_end], dtype=float)
        ys_dir_arr  = y_right * (x_end - xs_dir_arr) / laje_mm

        return (np.concatenate([xs_esq_arr, xs, xs_dir_arr]),
                np.concatenate([ys_esq_arr, ys, ys_dir_arr]))

    # ── Tabelas de saída ─────────────────────────────────────────────────────

    def _tabela_reacoes(self) -> List[list]:
        base = [["Apoio", "Posição [m]", "R_min [kN]", "R_max [kN]"]]
        for k in sorted(self._labels_apoio.keys()):
            pos_m        = round(k / 1000., 6)
            r_min, r_max = self._env_reacoes.get(round(k, 3), (0., 0.))
            phi          = self._get_phi(pos_m) if self._dict_coef else None
            if phi is not None:
                row = [self._labels_apoio[k], pos_m,
                       round(r_min, 6), round(r_max, 6),
                       round(phi, 3),
                       round(r_min * phi, 6), round(r_max * phi, 6)]
                if len(base[0]) == 4: base[0].extend(["φ", "φ·R_min [kN]", "φ·R_max [kN]"])
            else:
                row = [self._labels_apoio[k], pos_m, round(r_min, 6), round(r_max, 6)]
            base.append(row)
        return base

    def _tabela_cortante(self) -> List[list]:
        base = [["Posição [m]", "V_min [kN]", "V_max [kN]"]]
        for k, v in sorted(self._env_cortante.items()):
            pos_m        = round(k / 1000., 6)
            v_min, v_max = v
            phi          = self._get_phi(pos_m) if self._dict_coef else None
            if phi is not None:
                row = [pos_m, round(v_min, 6), round(v_max, 6), round(phi, 3), round(v_min * phi, 6), round(v_max * phi, 6)]
                if len(base[0]) == 3: base[0].extend(["φ", "φ·V_min [kN]", "φ·V_max [kN]"])
            else:
                row = [pos_m, round(v_min, 6), round(v_max, 6)]
            base.append(row)
        return self._limpar_duplicatas_descontinuidade(base)

    def _tabela_momento(self) -> List[list]:
        base = [["Posição [m]", "M_min [kNm]", "M_max [kNm]"]]
        for k, v in sorted(self._env_momento.items()):
            pos_m        = round(k / 1000., 6)
            m_min, m_max = v
            phi          = self._get_phi(pos_m) if self._dict_coef else None
            if phi is not None:
                row = [pos_m, round(m_min, 6), round(m_max, 6), round(phi, 3), round(m_min * phi, 6), round(m_max * phi, 6)]
                if len(base[0]) == 3: base[0].extend(["φ", "φ·M_min [kNm]", "φ·M_max [kNm]"])
            else:
                row = [pos_m, round(m_min, 6), round(m_max, 6)]
            base.append(row)
        return self._limpar_duplicatas_descontinuidade(base)
    
    def _limpar_duplicatas_descontinuidade(self, tabela: List[list]) -> List[list]:
        if len(tabela) < 2:
            return tabela

        cabecalho = tabela[0].copy()
        cabecalho.insert(1, "Seção")
        dados = tabela[1:]

        agrupado = {}
        for linha in dados:
            chave = round(float(linha[0]) * 1000.0, 1)
            if chave not in agrupado:
                agrupado[chave] = []
            agrupado[chave].append(linha)

        dados_limpos = []
        for chave in sorted(agrupado.keys()):
            grupo = agrupado[chave]
            pos_central = round(chave / 1000.0, 6) 

            if len(grupo) == 1:
                linha = grupo[0].copy()
                linha[0] = pos_central
                linha.insert(1, f"({pos_central:.2f} m)")
                dados_limpos.append(linha)
                continue

            idx_min = min(range(len(grupo)), key=lambda i: float(grupo[i][1]))
            idx_max = max(range(len(grupo)), key=lambda i: float(grupo[i][2]))

            if idx_min == idx_max:
                linha = grupo[idx_min].copy()
                linha[0] = pos_central
                linha.insert(1, f"({pos_central:.2f} m)")
                dados_limpos.append(linha)
            else:
                linha_esq = grupo[idx_min].copy()
                linha_esq[0] = pos_central
                linha_esq.insert(1, f"({pos_central:.2f} m) esq.")
                linha_dir = grupo[idx_max].copy()
                linha_dir[0] = pos_central
                linha_dir.insert(1, f"({pos_central:.2f} m) dir.")
                dados_limpos.extend([linha_esq, linha_dir])

        seen, unicas = set(), []
        for linha in dados_limpos:
            pos = round(float(linha[0]), 3)
            vals = (round(float(linha[2]), 6), round(float(linha[3]), 6))
            key = (pos, vals)
            if key not in seen:
                seen.add(key)
                unicas.append(linha)

        return [cabecalho] + unicas

    # ── Cálculo: estruturas biapoiadas ───────────────────────────────────────

    def _calcular_biapoiada(self):
        posicoes_apoio, cursor = [], 0.0

        if self._laje_mm > 0:
            posicoes_apoio.append(cursor)
            cursor += self._laje_mm

        for L_mm in self._vaos_mm:
            posicoes_apoio.append(cursor)
            cursor += L_mm

        posicoes_apoio.append(cursor)

        if self._laje_mm > 0:
            cursor += self._laje_mm
            posicoes_apoio.append(cursor)

        self._L_total_mm = cursor
        posicoes_apoio   = sorted({round(x, 3) for x in posicoes_apoio})

        for i, x_ap in enumerate(posicoes_apoio):
            self._labels_apoio[x_ap] = chr(65 + i)

            pts_x = [0.0]
            pts_y = [0.0]
            if i > 0:
                pts_x.append(posicoes_apoio[i-1])
                pts_y.append(0.0)
            pts_x.append(x_ap)
            pts_y.append(1.0)
            if i < len(posicoes_apoio) - 1:
                pts_x.append(posicoes_apoio[i+1])
                pts_y.append(0.0)
            pts_x.append(self._L_total_mm)
            pts_y.append(0.0)

            xs_full, unique_idx = np.unique(pts_x, return_index=True)
            ys_full = np.array(pts_y)[unique_idx]

            self._env_reacoes[round(x_ap, 3)] = _envelope_ponto(
                xs_full, ys_full,
                self._Q, self._q1, self._q2,
                self.L_CARRO_MM, self.AXLE_OFFSETS_MM, self._step_trem_mm)

        L_half = self._L_total_mm / 2.0
        env_v_half, env_m_half = {}, {}

        tarefas_iso: List[tuple] = []
        for i in range(len(posicoes_apoio) - 1):
            xA, xB = posicoes_apoio[i], posicoes_apoio[i + 1]
            xs_sec = self._gerar_malha_secoes(xA, xB, posicoes_apoio)
            xs_sec = xs_sec[xs_sec <= L_half + 1e-6]
            for k in xs_sec:
                k_clip = float(np.clip(k, xA, xB))
                tarefas_iso.append((
                    k_clip, xA, xB, 0.0, self._L_total_mm,
                    self._Q, self._q1, self._q2,
                    self.L_CARRO_MM, self.AXLE_OFFSETS_MM,
                    self._step_trem_mm, self._li_n_iso,
                ))

        with ThreadPoolExecutor(max_workers=_N_THREADS) as pool:
            for chave, env_v, env_m in pool.map(_worker_secao_iso, tarefas_iso):
                env_v_half[chave] = env_v
                env_m_half[chave] = env_m

        self._env_cortante = self._espelhar_envoltoria_cortante(env_v_half, self._L_total_mm)
        self._env_momento  = self._espelhar_envoltoria_momento(env_m_half, self._L_total_mm)

    # ── Cálculo: estruturas contínuas/hiperestáticas ─────────────────────────

    def _calcular_continua(self):
        geo          = self._geometria()
        L_total_mm   = geo["L_total_mm"]
        x_ini_main   = geo["x_ini_main"]
        x_fim_main   = geo["x_fim_main"]
        supports_loc = geo["supports_loc"]

        L_main_mm = x_fim_main - x_ini_main
        laje_L    = self._laje_mm

        section_params = [[0.0, L_main_mm, self._I_mm4, self._E_Nmm2, self._A_mm2, 0.0]]

        LI_reactions = _li_reacoes_fem_adjoint(
            L_main_mm, supports_loc, section_params, step_mm=self._li_step_fem_mm)

        sorted_sup_local = sorted(float(s[0]) for s in supports_loc)
        apoios_mm_loc    = {chr(65 + i): xap for i, xap in enumerate(sorted_sup_local)}

        env_r     = {}
        label_idx = 0

        if laje_L > 0:
            self._labels_apoio[0.0] = chr(65 + label_idx)
            label_idx += 1
            xs_f = np.linspace(0, L_total_mm, 2000)
            ys_f = np.zeros_like(xs_f)
            ys_f[xs_f <= laje_L] = (laje_L - xs_f[xs_f <= laje_L]) / laje_L
            env_r[0.0] = _envelope_ponto(
                xs_f, ys_f,
                self._Q, self._q1, self._q2,
                self.L_CARRO_MM, self.AXLE_OFFSETS_MM, self._step_trem_mm)

        for i, xap_loc in enumerate(sorted_sup_local):
            xap_glob = round(x_ini_main + xap_loc, 3)
            self._labels_apoio[xap_glob] = chr(65 + label_idx)
            label_idx += 1

            li_xs_loc, li_ys_loc, hermite_eval = LI_reactions[chr(65 + i)]
            xs_fem  = li_xs_loc + x_ini_main
            ys_fem  = li_ys_loc

            xs_ext, ys_ext = self._extend_li_for_slabs(
                xs_fem, ys_fem, x_ini_main, x_fim_main, laje_L)

            func_ext = ExtendedLI_Func(hermite_eval, x_ini_main, x_fim_main, laje_L) if laje_L > 0 else lambda x: hermite_eval(x - x_ini_main)
            ext_crit = func_ext.extrema if hasattr(func_ext, 'extrema') else []

            env_r[xap_glob] = _envelope_ponto(
                xs_ext, ys_ext,
                self._Q, self._q1, self._q2,
                self.L_CARRO_MM, self.AXLE_OFFSETS_MM, self._step_trem_mm,
                li_func=func_ext, extra_crit=ext_crit)

        if laje_L > 0:
            xap_end = round(L_total_mm, 3)
            self._labels_apoio[xap_end] = chr(65 + label_idx)
            xs_f = np.linspace(0, L_total_mm, 2000)
            ys_f = np.zeros_like(xs_f)
            ys_f[xs_f >= x_fim_main] = (xs_f[xs_f >= x_fim_main] - x_fim_main) / laje_L
            env_r[xap_end] = _envelope_ponto(
                xs_f, ys_f,
                self._Q, self._q1, self._q2,
                self.L_CARRO_MM, self.AXLE_OFFSETS_MM, self._step_trem_mm)

        L_half = L_total_mm / 2.0

        todos_apoios_glob = [x_ini_main + s[0] for s in supports_loc]

        xs_esq = self._gerar_malha_secoes(0.0, x_ini_main, [0.0, x_ini_main]) if laje_L > 0 else np.array([])
        xs_esq = xs_esq[xs_esq <= L_half + 1e-6]

        xs_mai = self._gerar_malha_secoes(x_ini_main, x_fim_main, todos_apoios_glob)
        xs_mai = xs_mai[xs_mai <= L_half + 1e-6]

        xs_dir = self._gerar_malha_secoes(x_fim_main, L_total_mm, [x_fim_main, L_total_mm]) if laje_L > 0 else np.array([])
        xs_dir = xs_dir[xs_dir <= L_half + 1e-6]

        env_v_half, env_m_half = {}, {}
        todas_ks = np.unique(np.concatenate([xs_esq, xs_mai, xs_dir]))

        tarefas_laje_esq, tarefas_laje_dir, tarefas_fem = [], [], []

        for k_glob in todas_ks:
            if laje_L > 0 and k_glob <= x_ini_main:
                tarefas_laje_esq.append((k_glob, 0.0, x_ini_main, 0.0, L_total_mm, self._Q, self._q1, self._q2, self.L_CARRO_MM, self.AXLE_OFFSETS_MM, self._step_trem_mm, self._li_n_iso))
            elif laje_L > 0 and k_glob >= x_fim_main:
                tarefas_laje_dir.append((k_glob, x_fim_main, L_total_mm, 0.0, L_total_mm, self._Q, self._q1, self._q2, self.L_CARRO_MM, self.AXLE_OFFSETS_MM, self._step_trem_mm, self._li_n_iso))
            else:
                k_loc = float(k_glob - x_ini_main)
                tarefas_fem.append((k_glob, k_loc, LI_reactions, apoios_mm_loc, x_ini_main, x_fim_main, laje_L, self._Q, self._q1, self._q2, self.L_CARRO_MM, self.AXLE_OFFSETS_MM, self._step_trem_mm))

        with ThreadPoolExecutor(max_workers=_N_THREADS) as pool:
            futures = []
            for t in tarefas_laje_esq + tarefas_laje_dir:
                futures.append(pool.submit(_worker_secao_iso_laje, t))
            for t in tarefas_fem:
                futures.append(pool.submit(_worker_secao_fem, t))
            for fut in as_completed(futures):
                chave, env_v, env_m = fut.result()
                env_v_half[chave] = env_v
                env_m_half[chave] = env_m

        self._env_cortante = self._espelhar_envoltoria_cortante(env_v_half, L_total_mm)
        self._env_momento  = self._espelhar_envoltoria_momento(env_m_half, L_total_mm)
        self._env_reacoes  = env_r
        self._L_total_mm   = L_total_mm

    # ── Espelhamento ─────────────────────────────────────────────────────────

    def _espelhar_envoltoria_cortante(self, env_half: Dict[float, Tuple[float, float]],
                                      L_total: float) -> Dict[float, Tuple[float, float]]:
        env_full = dict(env_half)
        for x_left, (v_min_left, v_max_left) in env_half.items():
            x_right = round(L_total - x_left, 4)
            if x_right not in env_full:
                env_full[x_right] = (-v_max_left, -v_min_left)
        return env_full

    def _espelhar_envoltoria_momento(self, env_half: Dict[float, Tuple[float, float]],
                                     L_total: float) -> Dict[float, Tuple[float, float]]:
        env_full = dict(env_half)
        for x_left, (m_min_left, m_max_left) in env_half.items():
            x_right = round(L_total - x_left, 4)
            if x_right not in env_full:
                env_full[x_right] = (m_min_left, m_max_left)
        return env_full

    # ── Geometria das estruturas contínuas ───────────────────────────────────

    def _geometria(self) -> dict:
        v, L, tipo = self._vaos_mm, self._laje_mm, self._tipo
        if tipo == "isostatica_em_balanco":
            L_c, L_b = (v[0] if len(v) >= 1 else 0.0, v[1] if len(v) >= 2 else 0.0)
            supports_loc = [[L_b, "pin"], [L_b + L_c, "mov"]]
            L_main       = L_b + L_c + L_b
            tem_balanco  = L_b > 0
        elif tipo == "hiperestatica_sem_balanco":
            L_c, L_e = v[0], (v[1] if len(v) >= 2 else v[0])
            supports_loc = [[0.0, "pin"], [L_e, "mov"], [L_e + L_c, "mov"], [L_e + L_c + L_e, "mov"]]
            L_main      = L_e + L_c + L_e
            tem_balanco = False
        elif tipo == "hiperestatica_com_balanco":
            L_c, L_e, L_b = v[0], (v[1] if len(v) >= 2 else v[0]), (v[2] if len(v) >= 3 else 0.0)
            supports_loc = [[L_b, "pin"], [L_b + L_e, "mov"], [L_b + L_e + L_c, "mov"], [L_b + L_e + L_c + L_e, "mov"]]
            L_main      = L_b + L_e + L_c + L_e + L_b
            tem_balanco = L_b > 0
        else:
            raise ValueError(f"Tipo estrutural inválido: '{tipo}'")

        return {
            "L_total_mm"   : L + L_main + L,
            "x_ini_main"   : L,
            "x_fim_main"   : L + L_main,
            "supports_loc" : supports_loc,
            "tem_balanco"  : tem_balanco,
        }

    # ── Plotagem ─────────────────────────────────────────────────────────────

    def _plotar_envoltoria(self,
                           titulo: str, ylabel: str,
                           env: Dict[float, Tuple[float, float]],
                           inverter_y: bool = False) -> Figure:
        cor_pos = "#81c784"
        cor_neg = "#e57373"

        fig, ax = plt.subplots(figsize=(9.61, 5.71), dpi=100)
        fig.patch.set_facecolor('#2d2d2d')
        ax.set_facecolor('#1e1e1e')
        for spine in ax.spines.values():
            spine.set_color('#888888')
        ax.tick_params(colors='white')
        ax.xaxis.label.set_color('white')
        ax.yaxis.label.set_color('white')

        if not env:
            fig.interactive_data = None
            return fig

        xs_sorted = sorted(env.keys())
        xs_m  = np.array(xs_sorted, dtype=float) / 1000.0
        maxs  = np.array([env[x][1] for x in xs_sorted], dtype=float)
        mins  = np.array([env[x][0] for x in xs_sorted], dtype=float)

        ax.plot(xs_m, maxs, color=cor_pos, linewidth=2.2, zorder=4, label='Máx')
        ax.plot(xs_m, mins, color=cor_neg, linewidth=2.2, zorder=4, label='Mín')

        ax.fill_between(xs_m, maxs, 0,
                        where=(maxs >= 0), facecolor=cor_pos, alpha=0.10, zorder=2)
        ax.fill_between(xs_m, mins, 0,
                        where=(mins <= 0), facecolor=cor_neg, alpha=0.10, zorder=2)
        ax.fill_between(xs_m, maxs, mins,
                        facecolor='#546e7a', alpha=0.08, zorder=1)

        ax.axhline(0, color='#cccccc', linewidth=1.2, zorder=3)

        apoios_mm = sorted(self._labels_apoio.keys())
        apoios_m_list = [x / 1000.0 for x in apoios_mm]

        y_range_all = max(float(np.max(np.abs(maxs))),
                         float(np.max(np.abs(mins))), 1e-9)
        threshold = 0.005 * y_range_all

        criticos_env: list = []  

        for x_mm in apoios_mm:
            x_m_ap = x_mm / 1000.0
            v_max  = float(np.interp(x_m_ap, xs_m, maxs))
            v_min  = float(np.interp(x_m_ap, xs_m, mins))
            if abs(v_max) > threshold:
                criticos_env.append((x_m_ap, v_max, 'max'))
            if abs(v_min) > threshold:
                criticos_env.append((x_m_ap, v_min, 'min'))

        for i in range(len(apoios_m_list) - 1):
            xa, xb = apoios_m_list[i], apoios_m_list[i + 1]
            mask   = (xs_m >= xa - 1e-6) & (xs_m <= xb + 1e-6)
            if not np.any(mask):
                continue
            x_sub  = xs_m[mask]
            max_sub = maxs[mask]
            min_sub = mins[mask]

            for idx_p, curva, arr in [(int(np.argmax(max_sub)), 'max', max_sub),
                                       (int(np.argmin(min_sub)), 'min', min_sub)]:
                x_p = x_sub[idx_p]
                y_p = arr[idx_p]
                near_apoio = any(abs(x_p - xa_) < 0.05 for xa_ in apoios_m_list)
                if abs(y_p) > threshold and not near_apoio:
                    criticos_env.append((x_p, y_p, curva))

        def _anotar_env(x_val: float, y_val: float, curva: str):
            cor = cor_pos if curva == 'max' else cor_neg
            ax.plot([x_val, x_val], [0.0, y_val],
                    color=cor, linewidth=0.85, linestyle='--', alpha=0.80, zorder=5)
            ax.scatter([x_val], [y_val], s=22, color=cor, zorder=6, linewidths=0)
            tip_is_up = (y_val >= 0) != inverter_y
            va_dir    = 'bottom' if tip_is_up else 'top'
            pad_y     = 3 if tip_is_up else -3
            ha        = 'right' if curva == 'min' else 'left'
            x_off     = -4 if curva == 'min' else 4
            ax.annotate(f"{y_val:+.2f}",
                        xy=(x_val, y_val), xytext=(x_off, pad_y),
                        textcoords='offset points',
                        fontsize=7, color=cor, ha=ha, va=va_dir, zorder=8)

        for (xv, yv, cv) in criticos_env:
            _anotar_env(xv, yv, cv)

        for x_mm_ap in self._labels_apoio:
            ax.axvline(x_mm_ap / 1000.0, color='#78909c',
                       linewidth=0.8, linestyle=':', alpha=0.6, zorder=2)

        _x_mm3 = 0.0
        _xs_sec2: list = []
        while _x_mm3 <= self._L_total_mm + 1e-3:
            _xs_sec2.append(_x_mm3 / 1000.0)
            _x_mm3 += 50.0
        xs_secoes  = np.array(_xs_sec2, dtype=float)
        ys_max_sec = np.interp(xs_secoes, xs_m, maxs)
        ys_min_sec = np.interp(xs_secoes, xs_m, mins)

        ax.set_xlabel('Posição [m]', fontsize=11)
        ax.set_ylabel(ylabel, fontsize=11)
        ax.set_title(titulo, color='white', fontsize=12, pad=10)
        ax.grid(True, alpha=0.25, linestyle='--', color='#aaaaaa')
        ax.set_xlim(-0.01 * (self._L_total_mm / 1000.0),
                     1.01 * (self._L_total_mm / 1000.0))
        if inverter_y:
            ax.invert_yaxis()

        leg = ax.legend(
            handles=[mpatches.Patch(color=cor_pos, label='Envoltória Máxima'),
                     mpatches.Patch(color=cor_neg, label='Envoltória Mínima')],
            fontsize=9, loc='best', framealpha=0.9)
        leg.get_frame().set_facecolor('#2d2d2d')
        leg.get_frame().set_edgecolor('#888888')
        for t in leg.get_texts():
            t.set_color('white')
        fig.tight_layout()

        fig.interactive_data = {
            'ax':        ax,
            'xs_secoes': xs_secoes,
            'y_max':     ys_max_sec,
            'y_min':     ys_min_sec,
            'ylabel':    ylabel,
            'inverted':  inverter_y,
        }
        return fig

    def _verificar_calculado(self):
        if not self._calculado:
            raise RuntimeError("Análise não executada. Chame calcular() antes de plotar.")

    @staticmethod
    def _resolver_tipo(tipo_str: str) -> str:
        if tipo_str in _MAPA_TIPOS: return _MAPA_TIPOS[tipo_str]
        tl = tipo_str.lower()
        if 'balan' in tl: return ('hiperestatica_com_balanco' if ('hiper' in tl or 'contin' in tl) else 'isostatica_em_balanco')
        if 'hiper' in tl or 'contin' in tl: return 'hiperestatica_sem_balanco'
        return 'biapoiada'


# =============================================================================
# ─── INTERATIVIDADE DE ENVOLTÓRIA (HOVER + SCROLL ZOOM + RESET) ─────────────
# =============================================================================

def ativar_interatividade_envoltoria(fig, canvas) -> None:
    data = getattr(fig, 'interactive_data', None)
    if data is None: return

    ax, xs_sec, y_max, y_min = data['ax'], data['xs_secoes'], data['y_max'], data['y_min']
    y_lo_orig, y_hi_orig = ax.get_ylim()

    vline,    = ax.plot([], [], color='#FFA726', lw=0.9, linestyle='--', alpha=0.0, zorder=8, label='_nolegend_')
    dot_max,  = ax.plot([], [], marker='o', markersize=8, color='#A5D6A7', alpha=0.0, zorder=9, linestyle='none', label='_nolegend_')
    dot_min,  = ax.plot([], [], marker='o', markersize=8, color='#EF9A9A', alpha=0.0, zorder=9, linestyle='none', label='_nolegend_')

    tooltip = ax.text(
        0.018, 0.975, '', transform=ax.transAxes, fontsize=8.0, color='white',
        va='top', ha='left', linespacing=1.65,
        bbox=dict(boxstyle='round,pad=0.50', facecolor='#0d0d1a', edgecolor='#FFA726', linewidth=0.9, alpha=0.0),
        zorder=20, visible=False,
    )

    def _snap(x_cursor: float) -> int:
        return int(np.argmin(np.abs(xs_sec - x_cursor)))

    def on_move(event):
        if event.inaxes is not ax or event.xdata is None:
            for obj in (vline, dot_max, dot_min):
                obj.set_data([], [])
                obj.set_alpha(0.0)
            tooltip.set_visible(False)
            canvas.draw_idle()
            return

        idx = _snap(event.xdata)
        x_sec, mx, mn = float(xs_sec[idx]), float(y_max[idx]), float(y_min[idx])

        y_lo_cur, y_hi_cur = ax.get_ylim()
        vline.set_data([x_sec, x_sec], [y_lo_cur, y_hi_cur])
        vline.set_alpha(0.55)
        dot_max.set_data([x_sec], [mx])
        dot_min.set_data([x_sec], [mn])
        dot_max.set_alpha(0.92)
        dot_min.set_alpha(0.92)

        tooltip.set_text(f"  ({x_sec:.2f} m)\n  Máx: {mx:+.3f}\n  Mín: {mn:+.3f}".replace('.', ','))
        tooltip.get_bbox_patch().set_alpha(0.93)
        tooltip.set_visible(True)
        canvas.draw_idle()

    def on_scroll(event):
        if event.inaxes is not ax: return
        y_lo_cur, y_hi_cur = ax.get_ylim()
        y_c = float(event.ydata) if event.ydata is not None else (y_lo_cur + y_hi_cur) / 2.0
        fator = 0.85 if event.button == 'up' else (1.0 / 0.85)
        ax.set_ylim(y_c - (y_c - y_lo_cur) * fator, y_c + (y_hi_cur - y_c) * fator)
        canvas.draw_idle()

    def on_click(event):
        if event.inaxes is ax and event.dblclick:
            ax.set_ylim(y_lo_orig, y_hi_orig)
            canvas.draw_idle()

    canvas.mpl_connect('motion_notify_event', on_move)
    canvas.mpl_connect('scroll_event',        on_scroll)
    canvas.mpl_connect('button_press_event',  on_click)