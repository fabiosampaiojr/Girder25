# =============================================================================
# Calculadora_Elementos_Finitos.py
# =============================================================================
# Módulo autossuficiente para análise linear estática de vigas (isostáticas e
# hiperestáticas) submetidas a cargas permanentes e sobrecargas, utilizando o
# Método dos Elementos Finitos (MEF/FEM) com elementos de viga de Bernoulli‑Euler.
#
# ─── FUNCIONALIDADES ─────────────────────────────────────────────────────────
#   • Cálculo de reações de apoio, esforço cortante e momento fletor.
#   • Suporte a vigas isostáticas (biapoiadas simples, múltiplos vãos) e
#     hiperestáticas (vãos contínuos com ou sem balanços).
#   • Inclusão opcional de lajes de transição como tramos biapoiados.
#   • Geração de tabelas formatadas para exportação.
#   • Plotagem de diagramas com tema escuro e interatividade (hover + scroll).
#
# ─── UNIDADES INTERNAS ───────────────────────────────────────────────────────
#   Comprimento : mm
#   Força       : N  →  saídas convertidas para kN
#   Momento     : N·mm  →  saídas convertidas para kN·m
#   E           : N/mm²  (entrada em kN/cm², convertida internamente)
#   Inércia I   : mm⁴   (entrada em cm⁴, convertida internamente)
#   Área A      : mm²   (entrada em cm², convertida internamente)
#
# ─── CONVENÇÃO DE SINAIS ─────────────────────────────────────────────────────
#   Forças aplicadas   : positivas para baixo (gravidade)
#   Reações de apoio   : positivas para cima
#   Cortante V         : positivo quando a face esquerda sobe
#   Momento M          : positivo quando traciona fibras inferiores (sagging)
# =============================================================================

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
from matplotlib.collections import LineCollection
from scipy.integrate import cumulative_trapezoid as cumtrapz
from typing import List, Sequence, Union, Optional
from numpy.polynomial.legendre import leggauss

Number = Union[int, float]


# =============================================================================
# BLOCO 1 — MOTOR DE ELEMENTOS FINITOS (FEM)
# Funções de baixo nível: rigidez, montagem, solução e pós-processamento.
# Originalmente em: modules/Elementos_Finitos.py
# =============================================================================

def numeric_element_stiffness(I, E, A, L, theta_deg):
    """
    Calcula e retorna a matriz de rigidez GLOBAL (6×6) de um elemento de viga
    de Bernoulli‑Euler plano, já rotacionada pelo ângulo theta.

    A formulação inclui rigidez axial (EA/L) e rigidez à flexão (baseada em EI),
    sendo a matriz local transformada para coordenadas globais via:
        K_global = Tᵀ · K_local · T

    Parâmetros
    ----------
    I         : float — inércia à flexão da seção [mm⁴]
    E         : float — módulo de elasticidade [N/mm²]
    A         : float — área da seção transversal [mm²]
    L         : float — comprimento do elemento [mm]
    theta_deg : float — inclinação do elemento em relação à horizontal [°]

    Retorna
    -------
    Ke_global : np.ndarray (6×6) — matriz de rigidez em coordenadas globais
    """
    theta = np.radians(theta_deg)
    c = np.cos(theta)
    s = np.sin(theta)

    # ── Matriz de rigidez local (coordenadas do elemento) ─────────────────────
    # Graus de liberdade: [u1, v1, θ1, u2, v2, θ2]
    # Termos axiais (EA/L) e termos de flexão (12EI/L³, 6EI/L², 4EI/L, 2EI/L)
    Ke_local = np.array([
        [ E*A/L,            0,           0, -E*A/L,            0,           0],
        [     0,  12*E*I/L**3,  6*E*I/L**2,      0, -12*E*I/L**3,  6*E*I/L**2],
        [     0,   6*E*I/L**2,    4*E*I/L,      0,  -6*E*I/L**2,    2*E*I/L],
        [-E*A/L,            0,           0,  E*A/L,            0,           0],
        [     0, -12*E*I/L**3, -6*E*I/L**2,      0,  12*E*I/L**3, -6*E*I/L**2],
        [     0,   6*E*I/L**2,    2*E*I/L,      0,  -6*E*I/L**2,    4*E*I/L],
    ])

    # ── Matriz de transformação (global → local) ───────────────────────────────
    T = np.array([
        [ c,  s, 0,  0,  0, 0],
        [-s,  c, 0,  0,  0, 0],
        [ 0,  0, 1,  0,  0, 0],
        [ 0,  0, 0,  c,  s, 0],
        [ 0,  0, 0, -s,  c, 0],
        [ 0,  0, 0,  0,  0, 1],
    ])

    # ── Rigidez global: K_g = Tᵀ K_l T ────────────────────────────────────────
    Ke_global = T.T @ Ke_local @ T
    return Ke_global


def build_nodes_from_inputs(
    supports: Sequence[Sequence],
    concentrated_forces: Sequence[Sequence],
    section_params: Sequence[Sequence],
    *,
    round_to: Optional[int] = 0,
    as_numpy: bool = False,
    tol: float = 1e-6,
) -> Union[List[Number], np.ndarray]:
    """
    Gera a lista ordenada e sem repetições de coordenadas nodais a partir das
    entradas do problema estrutural.

    Os nós são determinados automaticamente pelas posições de:
      • Apoios (suportes)
      • Forças concentradas
      • Extremidades de cada trecho de seção transversal

    Parâmetros
    ----------
    supports            : [[x, 'tipo'], ...]
    concentrated_forces : [[x, Fy], ...]  (aceita listas com ≥1 item)
    section_params      : [[x_ini, x_fim, ...], ...]
    round_to            : int | None — casas decimais de arredondamento
                          (0 → inteiro, None → sem arredondamento + tol)
    as_numpy            : bool — se True retorna np.ndarray; se False retorna list
    tol                 : float — tolerância para fusão de nós próximos (só quando round_to=None)

    Retorna
    -------
    Lista ou array de coordenadas x únicas e ordenadas.
    """
    xs = []

    def _safe_x(entry):
        """Extrai coordenada x do primeiro item da entrada, com tratamento de erro."""
        if entry is None or len(entry) == 0:
            return None
        try:
            return float(entry[0])
        except Exception:
            return None

    # Coletar x de cada tipo de entrada
    for s in supports or []:
        x = _safe_x(s)
        if x is not None:
            xs.append(x)

    for f in concentrated_forces or []:
        x = _safe_x(f)
        if x is not None:
            xs.append(x)

    for sec in section_params or []:
        if sec is None:
            continue
        if len(sec) >= 1:
            x0 = _safe_x([sec[0]])
            if x0 is not None:
                xs.append(x0)
        if len(sec) >= 2:
            x1 = _safe_x([sec[1]])
            if x1 is not None:
                xs.append(x1)

    if len(xs) == 0:
        return np.array([], dtype=float) if as_numpy else []

    xs = np.asarray(xs, dtype=float)

    # ── Eliminação de duplicatas ───────────────────────────────────────────────
    if round_to is not None:
        xs_rounded = (np.round(xs).astype(int) if round_to == 0
                      else np.round(xs, round_to))
        uniq = np.unique(xs_rounded)
        out = uniq.astype(int) if round_to == 0 else uniq
    else:
        # Sem arredondamento: funde valores dentro da tolerância
        xs_sorted = np.sort(xs)
        uniq = [xs_sorted[0]]
        for val in xs_sorted[1:]:
            if abs(val - uniq[-1]) > tol:
                uniq.append(val)
        out = np.array(uniq)

    if as_numpy:
        return np.asarray(out)
    if isinstance(out, np.ndarray) and np.issubdtype(out.dtype, np.integer):
        return out.tolist()
    if np.allclose(np.mod(out.astype(float), 1.0), 0.0, atol=1e-9):
        return [int(x) for x in out.tolist()]
    return out.tolist()


def add_points_from_inputs(
    supports: list,
    concentrated_forces: list,
    nodes_x: list,
) -> list:
    """
    Cria a lista de pontos nodais com condições de contorno e forças aplicadas.

    Cada nó tem a estrutura:
        [x, Fx, Fy, M, u, v, rot]

    Incógnitas (a resolver) são representadas como strings ('Fy3', 'u2', etc.).
    Valores nulos conhecidos (forças zero em nós livres, deslocamentos prescritos)
    são armazenados como 0.
    Forças concentradas em apoios são armazenadas como tuplas:
        ('Fy3', -10000)  →  reação + força aplicada no mesmo GDL

    Tipos de apoio reconhecidos
    ---------------------------
    'fix' (engaste)  : u=0, v=0, rot=0
    'pin' (rótula)   : u=0, v=0, M=0
    'mov' (rolete)   : v=0, Fx=0, M=0

    Parâmetros
    ----------
    supports            : [[x, tipo], ...]
    concentrated_forces : [[x, Fy], ...]
    nodes_x             : lista de coordenadas dos nós (saída de build_nodes_from_inputs)

    Retorna
    -------
    points : list — estrutura nodal com condições de contorno aplicadas
    """
    # 1. Criar nós base: todas as grandezas como incógnitas simbólicas
    points = []
    for i, x in enumerate(nodes_x, start=1):
        points.append([x, f'Fx{i}', f'Fy{i}', f'M{i}', f'u{i}', f'v{i}', f'rot{i}'])

    # 2. Nós sem apoio: forças externas são zero
    x_supports = [float(s[0]) for s in supports or []]
    for p in points:
        if p[0] not in x_supports:
            p[1] = 0   # Fx
            p[2] = 0   # Fy
            p[3] = 0   # M

    def idx_by_x(xval: Number) -> int:
        """Retorna o índice do nó com coordenada x = xval."""
        for idx, p in enumerate(points):
            if abs(p[0] - xval) < 1e-6:
                return idx
        return -1

    # 3. Aplicar condições de contorno dos apoios
    for x_sup, sup_type in supports or []:
        idx = idx_by_x(float(x_sup))
        if idx == -1:
            raise ValueError(f"Apoio em x={x_sup} não encontrado na lista de nós.")

        typ = sup_type.lower()
        if typ == 'fix':       # Engaste: bloqueia todos os deslocamentos
            points[idx][3] = 0   # M = 0
            points[idx][4] = 0   # u = 0
            points[idx][5] = 0   # v = 0
        elif typ == 'mov':     # Rolete: bloqueia apenas v (translação vertical)
            points[idx][3] = 0   # M = 0
            points[idx][1] = 0   # Fx = 0
            points[idx][5] = 0   # v = 0
        elif typ == 'pin':     # Rótula: bloqueia u e v, rotação livre
            points[idx][3] = 0   # M = 0
            points[idx][4] = 0   # u = 0
            points[idx][5] = 0   # v = 0
        else:
            raise ValueError(f"Tipo de apoio desconhecido: '{typ}'. Use 'fix', 'pin' ou 'mov'.")

    # 4. Aplicar forças concentradas (acumular sobre o que já existe no nó)
    for x_f, Fy_value in concentrated_forces or []:
        idx = idx_by_x(float(x_f))
        if idx == -1:
            raise ValueError(
                f"Força concentrada em x={x_f} não encontrada na lista de nós. "
                f"(Nós: {[p[0] for p in points]})"
            )
        current = points[idx][2]
        if isinstance(current, (int, float)):
            points[idx][2] = current + Fy_value
        elif isinstance(current, str):
            points[idx][2] = (current, Fy_value)       # símbolo + valor numérico
        elif isinstance(current, tuple):
            points[idx][2] = current + (Fy_value,)     # acumula mais um valor
        else:
            raise TypeError(f"Tipo inesperado em Fy do nó x={x_f}: {type(current)}")

    return points


def apply_distributed_loads_bulk(
    points: list,
    distributed_loads: list,
    n_gauss: int = 8,
) -> list:
    """
    Converte cargas distribuídas em forças e momentos nodais equivalentes
    usando integração de Gauss-Legendre (funções de forma de Hermite).

    A distribuição linear q(x) entre x_start e x_end é integrada sobre cada
    elemento que intercepta essa faixa. Os termos equivalentes são:
        Fy_esq = ∫ N₁(x)·q(x) dx
        M_esq  = ∫ N₂(x)·q(x) dx
        Fy_dir = ∫ N₃(x)·q(x) dx
        M_dir  = ∫ N₄(x)·q(x) dx

    onde N₁…N₄ são as funções de forma cúbicas de Hermite.

    Parâmetros
    ----------
    points           : lista de nós (saída de add_points_from_inputs)
    distributed_loads: [[x_start, q_start, x_end, q_end], ...]
                       q em N/mm (intensidade de carga linear)
    n_gauss          : int — número de pontos de Gauss (padrão 8)

    Retorna
    -------
    points : lista atualizada in-place com as contribuições das cargas distribuídas
    """
    if not distributed_loads:
        return points

    def make_qfunc(x0, q0, x1, q1):
        """Interpolação linear da intensidade q entre x0 e x1."""
        if x1 == x0:
            return lambda x: float(q0)
        return lambda x: q0 + (q1 - q0) * (x - x0) / (x1 - x0)

    def add_to_point(idx_pt: int, slot: int, value: float):
        """Acumula um valor numérico no slot de um ponto nodal."""
        cur = points[idx_pt][slot]
        if isinstance(cur, (int, float)):
            points[idx_pt][slot] = cur + value
        elif isinstance(cur, str):
            points[idx_pt][slot] = (cur, value)
        elif isinstance(cur, tuple):
            points[idx_pt][slot] = cur + (value,)
        else:
            raise TypeError(f"Tipo não suportado {type(cur)} no nó {idx_pt}, slot {slot}")

    for x_start, q_start, x_end, q_end in distributed_loads:
        qfunc = make_qfunc(x_start, q_start, x_end, q_end)

        for i in range(len(points) - 1):
            xe = points[i][0]
            xf = points[i + 1][0]

            # Interseção entre o elemento e a faixa de carga
            a = max(xe, min(x_start, x_end))
            b = min(xf, max(x_start, x_end))
            if b <= a:
                continue   # elemento fora da faixa

            L_elem = xf - xe
            s_a, s_b = a - xe, b - xe

            # Pontos e pesos de Gauss-Legendre
            gp, gw = leggauss(n_gauss)
            s_mid  = 0.5 * (s_b + s_a)
            s_half = 0.5 * (s_b - s_a)
            s_pts  = s_mid + s_half * gp
            w_pts  = gw * s_half

            # Vetor de forças locais equivalentes [Fy_esq, M_esq, Fy_dir, M_dir]
            fe_local = np.zeros(4, dtype=float)
            for s, w in zip(s_pts, w_pts):
                xi = s / L_elem
                # Funções de forma de Hermite (cúbicas)
                N1 = 1 - 3*xi**2 + 2*xi**3
                N2 = L_elem * (xi - 2*xi**2 + xi**3)
                N3 = 3*xi**2 - 2*xi**3
                N4 = L_elem * (-xi**2 + xi**3)
                Nvec = np.array([N1, N2, N3, N4])
                qx = float(qfunc(xe + s))
                fe_local += Nvec * qx * w

            add_to_point(i,   2, fe_local[0])   # Fy esquerdo
            add_to_point(i,   3, fe_local[1])   # M  esquerdo
            add_to_point(i+1, 2, fe_local[2])   # Fy direito
            add_to_point(i+1, 3, fe_local[3])   # M  direito

    return points


def boundary_conditions(points: list):
    """
    Extrai os vetores globais de forças (F) e deslocamentos (U) da lista nodal.

    Estrutura de cada ponto: [x, Fx, Fy, M, u, v, rot]
      → F = [Fx1, Fy1, M1, Fx2, Fy2, M2, ...]   (3 entradas por nó)
      → U = [u1,  v1,  rot1, u2, v2,  rot2, ...]

    Incógnitas permanecem como strings; valores prescritos (zero) como int/float.

    Parâmetros
    ----------
    points : lista de nós

    Retorna
    -------
    F : np.ndarray[object] — vetor de forças
    U : np.ndarray[object] — vetor de deslocamentos
    """
    F = np.array([val for p in points for val in p[1:4]], dtype=object)
    U = np.array([val for p in points for val in p[4:7]], dtype=object)
    return F, U


def elements_generator_with_sections(points: list, section_params: list) -> tuple:
    """
    Gera a lista de elementos finitos e o número total de graus de liberdade (GDL).

    Para cada par de nós consecutivos é criado um elemento com:
        [I, E, A, L, theta_deg, dof1, dof2, dof3, dof4, dof5, dof6]

    A seção transversal de cada elemento é determinada pelo ponto médio do elemento
    cruzado com os intervalos definidos em section_params.

    Parâmetros
    ----------
    points        : lista de nós (saída de add_points_from_inputs)
    section_params: [[x_ini, x_fim, I, E, A, theta_deg], ...]

    Retorna
    -------
    elements  : list — lista de elementos
    total_dof : int  — número total de graus de liberdade do sistema
    """
    n_nodes = len(points)
    if n_nodes < 2:
        raise ValueError("São necessários ao menos dois nós para formar um elemento.")

    elements = []
    for i in range(1, n_nodes):
        x_left  = float(points[i - 1][0])
        x_right = float(points[i][0])
        L_elem  = x_right - x_left
        if L_elem <= 0:
            raise ValueError(
                f"Elemento com comprimento inválido entre x={x_left} e x={x_right}."
            )

        x_mid   = 0.5 * (x_left + x_right)
        matched = None
        for xs, xe, I, E, A, theta in section_params:
            if min(xs, xe) <= x_mid <= max(xs, xe):
                matched = (float(I), float(E), float(A), float(theta))
                break
        if matched is None:
            raise ValueError(f"Nenhuma seção cobre o ponto médio x={x_mid}.")

        I_, E_, A_, theta_ = matched
        gdl_start = (i - 1) * 3 + 1
        dofs = list(range(gdl_start, gdl_start + 6))
        elements.append([I_, E_, A_, L_elem, theta_, *dofs])

    total_dof = n_nodes * 3
    return elements, total_dof


def assemble_global_stiffness(K_elements: list, total_dof: int) -> np.ndarray:
    """
    Monta a matriz de rigidez global [n_dof × n_dof] por superposição das
    matrizes elementares.

    Cada Ke empacotada tem formato (7×7):
        Ke[0, 1:] = índices globais dos DOFs (base 1)
        Ke[1:, 1:] = submatriz de rigidez 6×6

    Parâmetros
    ----------
    K_elements : list[np.ndarray (7×7)] — matrizes elementares empacotadas
    total_dof  : int — número total de graus de liberdade

    Retorna
    -------
    K_global : np.ndarray (total_dof × total_dof) — matriz de rigidez global
    """
    K_global = np.zeros((total_dof, total_dof), dtype=float)
    for Ke in K_elements:
        GDL = Ke[0, 1:].astype(int) - 1   # índices 0-based
        for i in range(6):
            for j in range(6):
                K_global[GDL[i], GDL[j]] += Ke[i + 1, j + 1]
    return K_global


def solve_fem_numeric(
    K_global: np.ndarray,
    F_global: np.ndarray,
    fixed_dofs: list,
) -> tuple:
    """
    Resolve o sistema linear K_global · U = F_global com condições de contorno
    de Dirichlet homogêneas (apoios com deslocamento nulo).

    O método parte da partição:
        [K_rr  K_rf] [U_r]   [F_r]
        [K_fr  K_ff] [U_f] = [F_f]

    onde 'r' = livre (free) e 'f' = fixo.
    Resolve: K_rr · U_r = F_r − K_rf · U_f   (com U_f = 0)

    Reações: R = K · U − F  (não nulas apenas nos DOFs fixos)

    Parâmetros
    ----------
    K_global  : np.ndarray (n×n) — matriz de rigidez global
    F_global  : np.ndarray (n,)  — vetor global de forças
    fixed_dofs: list[int]        — índices dos DOFs com deslocamento fixo (base 0)

    Retorna
    -------
    U_full : np.ndarray (n,) — vetor completo de deslocamentos
    R      : np.ndarray (n,) — vetor de reações
    """
    total_dof = K_global.shape[0]
    free_dofs = [i for i in range(total_dof) if i not in fixed_dofs]

    K_rr = K_global[np.ix_(free_dofs, free_dofs)]
    K_rf = K_global[np.ix_(free_dofs, fixed_dofs)]
    F_r  = F_global[free_dofs]
    U_f  = np.zeros(len(fixed_dofs))

    U_r    = np.linalg.solve(K_rr, F_r - K_rf @ U_f)
    U_full = np.zeros(total_dof)
    U_full[free_dofs]  = U_r
    U_full[fixed_dofs] = U_f

    R = K_global @ U_full - F_global
    return U_full, R


def fem(
    supports: list,
    concentrated_forces: list,
    distributed_loads: list,
    section_params: list,
) -> tuple:
    """
    Orquestrador principal do Motor de Elementos Finitos para viga 2D.

    Executa o pipeline completo:
        1. Geração automática de nós
        2. Montagem da estrutura nodal com condições de contorno
        3. Transformação de cargas distribuídas em forças nodais equivalentes
        4. Extração dos vetores F e U
        5. Geração dos elementos com propriedades de seção
        6. Cálculo das matrizes de rigidez elementares
        7. Montagem da matriz de rigidez global
        8. Identificação dos DOFs fixos
        9. Solução do sistema linear

    Parâmetros
    ----------
    supports            : [[x_mm, tipo], ...]
                          Tipos aceitos: 'fix', 'pin', 'mov'
    concentrated_forces : [[x_mm, Fy_N], ...]
                          Positivo para baixo (convenção gravitacional)
    distributed_loads   : [[x_ini, q_ini, x_fim, q_fim], ...]
                          q em N/mm; interpolação linear entre extremos
    section_params      : [[x_ini, x_fim, I_mm4, E_Nmm2, A_mm2, theta_deg], ...]

    Retorna
    -------
    U_full  : np.ndarray — vetor de deslocamentos e rotações nodais
    R       : np.ndarray — vetor de reações em todos os GDLs
    nodes_x : list       — coordenadas X dos nós utilizados [mm]
    """
    # 1. Construir nós
    nodes_x = build_nodes_from_inputs(supports, concentrated_forces, section_params)

    # 2. Montar estrutura nodal com condições de contorno
    points = add_points_from_inputs(supports, concentrated_forces, nodes_x)

    # 3. Aplicar cargas distribuídas (equivalência nodal por Gauss-Hermite)
    points = apply_distributed_loads_bulk(points, distributed_loads)

    # 4. Vetores globais de forças e deslocamentos
    F, U = boundary_conditions(points)

    # 5. Gerar elementos e contagem de GDLs
    elements, total_dof = elements_generator_with_sections(points, section_params)

    # 6. Calcular e empacotar matrizes de rigidez elementares
    K_elements = []
    for el in elements:
        I, E, A, L, theta, *dofs = el
        Ke_global = numeric_element_stiffness(I, E, A, L, theta)
        Ke_packed = np.zeros((7, 7))
        Ke_packed[0, 1:]  = dofs
        Ke_packed[1:, 0]  = dofs
        Ke_packed[1:, 1:] = Ke_global
        K_elements.append(Ke_packed)

    # 7. Montar matriz de rigidez global
    K_global = assemble_global_stiffness(K_elements, total_dof)

    # 8. Identificar DOFs fixos (deslocamento = 0)
    fixed_dofs = [i for i, val in enumerate(U) if val == 0]

    # 9. Converter vetor de forças para numérico (somar tuplas, ignorar símbolos)
    def extract_numeric_force(f):
        if isinstance(f, (int, float)):
            return float(f)
        elif isinstance(f, tuple):
            return sum(v for v in f if isinstance(v, (int, float)))
        return 0.0

    F_numeric = np.array([extract_numeric_force(f) for f in F], dtype=float)

    # 10. Resolver o sistema
    U_full, R = solve_fem_numeric(K_global, F_numeric, fixed_dofs)
    return U_full, R, nodes_x


def sift_results(
    R: np.ndarray,
    nodes_x: list,
    supports: list,
    concentrated_forces: list,
    tol: float = 1e-6,
) -> tuple:
    """
    Filtra e separa as forças verticais nodais e as reações de apoio puras.

    O vetor R retornado pelo FEM contém reações PURAS (sem as forças aplicadas).
    Este método reconstrói dois dicionários:
      • forces_y         : reações + forças concentradas aplicadas (usado para V(x))
      • reaction_forces_y: somente as reações de apoio (para tabela de reações)

    Parâmetros
    ----------
    R                   : np.ndarray — vetor de reações nodais [Fx1, Fy1, M1, ...]
    nodes_x             : list — coordenadas x dos nós
    supports            : [[x, tipo], ...]
    concentrated_forces : [[x, Fy], ...]
    tol                 : float — threshold abaixo do qual Fy é zerado

    Retorna
    -------
    forces_y         : dict {x_mm: Fy_N} — todas as forças verticais
    reaction_forces_y: dict {x_mm: Fy_N} — reações puras nos apoios
    """
    # Extrair Fy de cada nó (índice 3i+1 no vetor global)
    forces_y = {
        x: R[3*i + 1] if abs(R[3*i + 1]) > tol else 0.0
        for i, x in enumerate(nodes_x)
    }

    # Reações puras (somente nós de apoio)
    coords_supports = {s[0] for s in supports}
    reaction_forces_y = {x: fy for x, fy in forces_y.items() if x in coords_supports}

    # Acrescentar forças concentradas ao dicionário completo
    for coord_x, force in concentrated_forces:
        if coord_x in forces_y:
            forces_y[coord_x] += force
        else:
            forces_y[coord_x] = force

    forces_y          = dict(sorted(forces_y.items()))
    reaction_forces_y = dict(sorted(reaction_forces_y.items()))
    return forces_y, reaction_forces_y


def calculate_shear_force(
    full_length: float,
    y_forces: dict,
    distributed_loads: list,
    dx: float = 1.0,
) -> dict:
    """
    Calcula o diagrama de esforço cortante V(x) por integração numérica
    progressiva (da esquerda para a direita), incorporando:
      • Cargas distribuídas lineares (regra dos trapézios)
      • Saltos concentrados nas posições de apoio e força pontual

    A malha de integração combina:
      • Pontos regulares espaçados de dx
      • Pontos exatos de descontinuidade (apoios, bordas de carga)
    garantindo precisão independentemente do valor de dx.

    Parâmetros
    ----------
    full_length        : float — comprimento total da viga [mm]
    y_forces           : dict {x_mm: Fy_N} — forças verticais (positivo para cima)
    distributed_loads  : [[x_ini, q_ini, x_fim, q_fim], ...] — em N/mm
    dx                 : float — passo base da malha de integração [mm]

    Retorna
    -------
    shear_dict : dict
        Chaves: 'x.3f'  (sem descontinuidade)
                'x.3fe' (valor à esquerda de salto)
                'x.3fd' (valor à direita de salto)
        Valores: V em kN
    """
    # ── Malha refinada: regular + pontos críticos ─────────────────────────────
    x_regular = np.arange(0.0, full_length + dx, dx, dtype=float)
    x_breaks  = [0.0, float(full_length)]
    x_breaks.extend(float(x) for x in y_forces.keys())
    for x_start, _, x_end, _ in distributed_loads:
        x_breaks.extend([float(x_start), float(x_end)])

    x_values = np.unique(np.round(np.concatenate([x_regular, x_breaks]), 6))
    x_values = x_values[(x_values >= -1e-6) & (x_values <= full_length + 1e-6)]
    if len(x_values) == 0:
        return {}
    x_values[0]  = 0.0
    x_values[-1] = float(full_length)

    # ── Intensidade q(x) na malha ─────────────────────────────────────────────
    q_total = np.zeros_like(x_values, dtype=float)
    for x_start, q_start, x_end, q_end in distributed_loads:
        x0 = float(min(x_start, x_end))
        x1 = float(max(x_start, x_end))
        if abs(x1 - x0) <= 1e-12:
            continue
        in_range = (x_values >= x0 - 1e-9) & (x_values <= x1 + 1e-9)
        t = (x_values[in_range] - x_start) / (x_end - x_start)
        q_total[in_range] += (1.0 - t) * float(q_start) + t * float(q_end)

    # ── Integração acumulada (regra dos trapézios) ─────────────────────────────
    dx_values = np.diff(x_values)
    delta_v   = 0.5 * (q_total[:-1] + q_total[1:]) * dx_values / 1000.0
    v_values  = np.concatenate([[0.0], np.cumsum(delta_v)])   # kN

    # ── Construção do dicionário com saltos ───────────────────────────────────
    shear_dict      = {}
    y_force_coords  = {round(float(x), 6): float(fy) for x, fy in y_forces.items()}

    for i, x in enumerate(x_values):
        x_round    = round(float(x), 6)
        x_key_str  = f"{x:.3f}"

        shear_dict[x_key_str] = v_values[i]

        if x_round in y_force_coords:
            # Descontinuidade: registrar valor antes e depois do salto
            shear_dict[f"{x_key_str}e"] = v_values[i]
            Fy_kN = y_force_coords[x_round] / 1000.0
            v_values[i:] += Fy_kN
            shear_dict[f"{x_key_str}d"] = v_values[i]
            shear_dict.pop(x_key_str, None)
            del y_force_coords[x_round]

    return shear_dict


def calculate_bending_moment_from_shear_fast(shear_dict: dict) -> dict:
    """
    Calcula o diagrama de momento fletor M(x) integrando numericamente V(x)
    pela regra dos trapézios cumulativa (vetorizada via scipy/numpy).

    Relação diferencial utilizada:
        dM/dx = V(x)   →   M(x) = ∫₀ˣ V(ξ) dξ

    Com condição de contorno M(0) = 0 (viga sem momento inicial).

    Parâmetros
    ----------
    shear_dict : dict — saída de calculate_shear_force {chave: V_kN}

    Retorna
    -------
    moment_dict : dict {'x.3f': M_kNm} — momento fletor em cada posição
    """
    # Extrair coordenadas numéricas (removendo sufixos 'e'/'d')
    X = np.array([float(k.rstrip('ed')) for k in shear_dict.keys()])
    V = np.array(list(shear_dict.values()))

    # Ordenar por posição
    sort_idx = np.argsort(X)
    X = X[sort_idx]
    V = V[sort_idx]

    # Integração cumulativa dos trapézios (resultado em kN·m, pois V em kN e X em mm/1000)
    M = cumtrapz(V, X, initial=0) / 1000.0

    moment_dict = {f"{x:.3f}": m for x, m in zip(X, M)}
    return moment_dict


# =============================================================================
# BLOCO 2 — MAPEAMENTO DE TIPOS ESTRUTURAIS
# =============================================================================

# Traduz o nome exibido na interface para o identificador interno do solver
_MAPA_TIPOS: dict[str, str] = {
    "Isostática: Múltiplos Vãos Biapoioados":    "biapoiada",
    "Isostática: Biapoiada com Balanço":         "isostatica_em_balanco",
    "Hiperestática: Vão Contínuo sem Balanço":   "hiperestatica_sem_balanco",
    "Hiperestática: Vão Contínuo com Balanço":   "hiperestatica_com_balanco",
}


# =============================================================================
# BLOCO 3 — CLASSE PRINCIPAL: CalculadoraElementosFinitos
# =============================================================================

class CalculadoraElementosFinitos:
    """
    Calculadora de esforços estáticos para superestruturas de pontes.

    Suporta os seguintes sistemas estruturais:
        • Isostática: múltiplos vãos biapoiados independentes
        • Isostática: vão com balanços laterais
        • Hiperestática: vão contínuo sem balanço (3 apoios internos)
        • Hiperestática: vão contínuo com balanço (4 apoios internos)

    Opcionalmente inclui lajes de transição nas extremidades, modeladas
    como vigas biapoiadas independentes cujas reações são transferidas
    ao vão principal.

    Parâmetros de Construção
    ------------------------
    superestrutura       : objeto com atributos:
                            .tipo            — string do tipo estrutural
                            .vaos            — list[float], comprimentos em metros
                            .laje_transicao  — float | False | None, em metros
    secao_superestrutura : objeto com .parametros_geometricos (dict):
                            'Ix'   — inércia [cm⁴]
                            'Area' — área    [cm²]
    acoes                : dict com:
                            'Carga Concentrada': [[F_kN, x_m, ...], ...]
                            'Carga Distribuída': [[q_kNm, x_ini_m, x_fim_m], ...]
    modulo_elasticidade  : float — módulo E em kN/cm²
    """

    def __init__(
        self,
        superestrutura,
        secao_superestrutura,
        acoes: dict,
        modulo_elasticidade: float,
    ):
        self._super     = superestrutura
        self._secao     = secao_superestrutura
        self._acoes_raw = acoes
        self._E_kN_cm2  = float(modulo_elasticidade)
        self._tipo      = self._resolver_tipo(superestrutura.tipo)

        # ── Conversão de unidades (entrada → sistema interno: mm, N) ─────────
        pg = secao_superestrutura.parametros_geometricos
        self._Ix_mm4 = float(pg["Ix"])   * 1e4      # cm⁴ → mm⁴
        self._A_mm2  = float(pg["Area"]) * 1e2      # cm² → mm²
        self._E_Nmm2 = float(modulo_elasticidade) * 10.0   # kN/cm² → N/mm²

        # ── Geometria em milímetros ───────────────────────────────────────────
        self._vaos_mm: list[float] = [v * 1e3 for v in superestrutura.vaos]
        self._laje_mm: float = 0.0
        if superestrutura.laje_transicao not in (False, None):
            self._laje_mm = float(superestrutura.laje_transicao) * 1e3

        # ── Resultados internos (preenchidos após calcular()) ─────────────────
        self._reacoes      : dict[float, float] = {}
        self._labels_apoio : dict[float, str]   = {}
        self._cortante     : dict               = {}
        self._momento      : dict               = {}
        self._L_total_mm   : float              = 0.0
        self._calculado    : bool               = False

    # =========================================================================
    # API PÚBLICA
    # =========================================================================

    def calcular(self) -> tuple[list, list, list]:
        """
        Executa a análise estrutural e retorna as três tabelas de resultados.

        Retorna
        -------
        (tabela_reacoes, tabela_cortante, tabela_momento)
        Cada tabela é uma list[list] com cabeçalho na primeira linha.
        """
        if self._tipo == "biapoiada":
            self._analisar_biapoiada()
        else:
            self._analisar_continua()
        self._calculado = True
        return (
            self._montar_tabela_reacoes(),
            self._montar_tabela_cortante(),
            self._montar_tabela_momento(),
        )

    def plotar_cortante(self) -> Figure:
        """Gera e retorna a figura Matplotlib do diagrama de esforço cortante."""
        self._verificar_calculado()
        return self._plotar_diagrama(
            "Diagrama de Esforço Cortante", "V [kN]",
            self._cortante, inverter_y=False
        )

    def plotar_momento(self) -> Figure:
        """Gera e retorna a figura Matplotlib do diagrama de momento fletor."""
        self._verificar_calculado()
        return self._plotar_diagrama(
            "Diagrama de Momento Fletor", "M [kN·m]",
            self._momento, inverter_y=True
        )

    # =========================================================================
    # ANÁLISE — ISOSTÁTICA (MÚLTIPLOS VÃOS BIAPOIADOS)
    # =========================================================================

    def _analisar_biapoiada(self):
        """
        Resolve cada vão biapoiado independentemente, acumulando reações e
        diagramas em um sistema de coordenadas global.

        Lajes de transição (esquerda e direita) são tratadas como vãos biapoiados
        adicionais, com suas reações acumuladas nos nós de extremidade.
        """
        cortante_global: dict = {}
        momento_global:  dict = {}
        posicoes_apoio:  list[float] = []
        cur = 0.0

        # ── Determinar posições de todos os apoios ────────────────────────────
        if self._laje_mm > 0:
            posicoes_apoio.append(cur)
            cur += self._laje_mm

        for L_mm in self._vaos_mm:
            posicoes_apoio.append(cur)
            cur += L_mm
        posicoes_apoio.append(cur)

        if self._laje_mm > 0:
            cur += self._laje_mm
            posicoes_apoio.append(cur)

        posicoes_apoio = sorted(set(round(x, 3) for x in posicoes_apoio))
        for i, xp in enumerate(posicoes_apoio):
            self._labels_apoio[xp] = chr(65 + i)   # A, B, C, ...

        cursor_mm = 0.0

        # ── Laje de transição esquerda ─────────────────────────────────────────
        if self._laje_mm > 0:
            R_e, R_d, sh_lj, mo_lj = self._analisar_laje_completa(cursor_mm, self._laje_mm)
            self._acumular_reacao(round(cursor_mm, 3), R_e)
            self._acumular_reacao(round(cursor_mm + self._laje_mm, 3), R_d)
            self._agregar_diagramas(sh_lj, mo_lj, cursor_mm, cortante_global, momento_global)
            cursor_mm += self._laje_mm

        # ── Vãos biapoiados principais ─────────────────────────────────────────
        for L_mm in self._vaos_mm:
            x_ini = cursor_mm
            x_fim = cursor_mm + L_mm
            suportes  = [[0.0, "pin"], [L_mm, "mov"]]
            secao_loc = [[0.0, L_mm, self._Ix_mm4, self._E_Nmm2, self._A_mm2, 0.0]]
            conc_loc, dist_loc = self._extrair_acoes_fem(x_ini, x_fim, offset_mm=x_ini)

            U, R_vec, nodes_x = fem(suportes, conc_loc, dist_loc, secao_loc)
            forces_y, reac_y  = sift_results(R_vec, nodes_x, suportes, conc_loc)
            sh_vao = calculate_shear_force(L_mm, forces_y, dist_loc, dx=10.0)
            mo_vao = calculate_bending_moment_from_shear_fast(sh_vao)

            self._acumular_reacao(round(x_ini, 3), self._reacao_em(reac_y, 0.0))
            self._acumular_reacao(round(x_fim, 3), self._reacao_em(reac_y, L_mm))
            self._agregar_diagramas(sh_vao, mo_vao, x_ini, cortante_global, momento_global)
            cursor_mm = x_fim

        # ── Laje de transição direita ──────────────────────────────────────────
        if self._laje_mm > 0:
            R_e, R_d, sh_lj, mo_lj = self._analisar_laje_completa(cursor_mm, self._laje_mm)
            self._acumular_reacao(round(cursor_mm, 3), R_e)
            self._acumular_reacao(round(cursor_mm + self._laje_mm, 3), R_d)
            self._agregar_diagramas(sh_lj, mo_lj, cursor_mm, cortante_global, momento_global)
            cursor_mm += self._laje_mm

        self._cortante, self._momento, self._L_total_mm = (
            cortante_global, momento_global, cursor_mm
        )

    # =========================================================================
    # ANÁLISE — HIPERESTÁTICA (VÃO CONTÍNUO)
    # =========================================================================

    def _analisar_continua(self):
        """
        Resolve a viga contínua com múltiplos apoios internos usando um único
        modelo FEM global para o vão principal.

        Lajes de transição são resolvidas separadamente como biapoiadas e suas
        reações são transferidas como cargas concentradas nas extremidades do
        vão principal (para o caso com balanços).
        """
        geo = self._calcular_geometria()
        L_total_mm  = geo["L_total_mm"]
        x_ini_main  = geo["x_ini_main"]
        x_fim_main  = geo["x_fim_main"]
        suportes_loc = geo["suportes_loc"]
        tem_balanco  = geo["tem_balanco"]
        L_main = x_fim_main - x_ini_main

        R_e_lj_esq = R_d_lj_esq = R_e_lj_dir = R_d_lj_dir = 0.0
        sh_lj_esq = mo_lj_esq = sh_lj_dir = mo_lj_dir = {}

        # ── Lajes de transição (se existirem) ─────────────────────────────────
        if self._laje_mm > 0:
            R_e_lj_esq, R_d_lj_esq, sh_lj_esq, mo_lj_esq = \
                self._analisar_laje_completa(0.0, self._laje_mm)
            R_e_lj_dir, R_d_lj_dir, sh_lj_dir, mo_lj_dir = \
                self._analisar_laje_completa(x_fim_main, self._laje_mm)

        # ── Ações no vão principal ─────────────────────────────────────────────
        conc_loc, dist_loc = self._extrair_acoes_fem(
            x_ini_main, x_fim_main, offset_mm=x_ini_main
        )

        # Transferência das reações de laje para o vão principal (balanços)
        if tem_balanco and self._laje_mm > 0:
            conc_loc.extend([[0.0, -R_d_lj_esq], [L_main, -R_e_lj_dir]])

        secao_loc = [[0.0, L_main, self._Ix_mm4, self._E_Nmm2, self._A_mm2, 0.0]]
        U, R_vec, nodes_x = fem(suportes_loc, conc_loc, dist_loc, secao_loc)
        forces_y, reac_y  = sift_results(R_vec, nodes_x, suportes_loc, conc_loc)

        sh_main = calculate_shear_force(L_main, forces_y, dist_loc, dx=10.0)
        mo_main = calculate_bending_moment_from_shear_fast(sh_main)

        cortante_global, momento_global, label_idx = {}, {}, 0

        # ── Montagem global dos resultados ─────────────────────────────────────
        if self._laje_mm > 0:
            self._labels_apoio[0.0] = chr(65 + label_idx); label_idx += 1
            self._acumular_reacao(0.0, R_e_lj_esq)
            if not tem_balanco:
                self._acumular_reacao(x_ini_main, R_d_lj_esq)
            self._agregar_diagramas(sh_lj_esq, mo_lj_esq, 0.0, cortante_global, momento_global)

        for s_loc in sorted(s[0] for s in suportes_loc):
            x_glob = round(x_ini_main + s_loc, 3)
            R_N = self._reacao_em(reac_y, s_loc)
            if x_glob not in self._labels_apoio:
                self._labels_apoio[x_glob] = chr(65 + label_idx); label_idx += 1
            self._acumular_reacao(x_glob, R_N)

        self._agregar_diagramas(sh_main, mo_main, x_ini_main, cortante_global, momento_global)

        if self._laje_mm > 0:
            if not tem_balanco:
                self._acumular_reacao(x_fim_main, R_e_lj_dir)
            x_ap_ext_dir = round(x_fim_main + self._laje_mm, 3)
            self._labels_apoio[x_ap_ext_dir] = chr(65 + label_idx); label_idx += 1
            self._acumular_reacao(x_ap_ext_dir, R_d_lj_dir)
            self._agregar_diagramas(sh_lj_dir, mo_lj_dir, x_fim_main, cortante_global, momento_global)

        self._cortante, self._momento, self._L_total_mm = (
            cortante_global, momento_global, L_total_mm
        )

    def _analisar_laje_completa(
        self,
        x_ini_global_mm: float,
        L_laje_mm: float,
    ) -> tuple[float, float, dict, dict]:
        """
        Resolve uma laje de transição como viga biapoiada isolada.

        Parâmetros
        ----------
        x_ini_global_mm : float — posição global de início da laje [mm]
        L_laje_mm       : float — comprimento da laje [mm]

        Retorna
        -------
        (R_esq, R_dir, shear_dict, moment_dict)
        Reações em N; diagramas em coordenadas locais (0…L_laje_mm).
        """
        suportes  = [[0.0, "pin"], [L_laje_mm, "mov"]]
        secao_loc = [[0.0, L_laje_mm, self._Ix_mm4, self._E_Nmm2, self._A_mm2, 0.0]]
        conc_loc, dist_loc = self._extrair_acoes_fem(
            x_ini_global_mm,
            x_ini_global_mm + L_laje_mm,
            offset_mm=x_ini_global_mm,
        )
        if not conc_loc and not dist_loc:
            return 0.0, 0.0, {}, {}

        U, R_vec, nodes_x = fem(suportes, conc_loc, dist_loc, secao_loc)
        forces_y, reac_y  = sift_results(R_vec, nodes_x, suportes, conc_loc)
        sh = calculate_shear_force(L_laje_mm, forces_y, dist_loc, dx=10.0)
        mo = calculate_bending_moment_from_shear_fast(sh)
        return self._reacao_em(reac_y, 0.0), self._reacao_em(reac_y, L_laje_mm), sh, mo

    def _calcular_geometria(self) -> dict:
        """
        Determina as coordenadas globais e a configuração dos apoios internos
        com base no tipo estrutural selecionado.

        Tipos e geometrias
        ------------------
        isostatica_em_balanco:
            [balanco]—[apoio_pin]—[vao_central]—[apoio_mov]—[balanco]

        hiperestatica_sem_balanco:
            [apoio_pin]—[extremo]—[vao_central]—[extremo]—[apoio_mov]
            com apoios adicionais nos pontos de inflexão

        hiperestatica_com_balanco:
            [balanco]—[apoio_pin]—[extremo]—[vão_central]—[extremo]—[apoio_mov]—[balanco]

        Retorna
        -------
        dict com chaves:
            'L_total_mm'   : comprimento total incluindo lajes
            'x_ini_main'   : início do vão principal [mm]
            'x_fim_main'   : fim do vão principal [mm]
            'suportes_loc' : [[x_local, tipo], ...] em coords do vão principal
            'tem_balanco'  : bool
        """
        v, L, tipo = self._vaos_mm, self._laje_mm, self._tipo

        if tipo == "isostatica_em_balanco":
            L_c, L_b = (v[0], v[1]) if len(v) >= 2 else (v[0], 0.0)
            L_main, x_ini_main = L_b + L_c + L_b, L
            suportes_loc = [[L_b, "pin"], [L_b + L_c, "mov"]]
            tem_balanco  = L_b > 0

        elif tipo == "hiperestatica_sem_balanco":
            L_c, L_e = v[0], v[1] if len(v) >= 2 else v[0]
            L_main, x_ini_main = L_e + L_c + L_e, L
            suportes_loc = [
                [0.0,         "pin"],
                [L_e,         "mov"],
                [L_e + L_c,   "mov"],
                [L_main,      "mov"],
            ]
            tem_balanco = False

        elif tipo == "hiperestatica_com_balanco":
            L_c = v[0]
            L_e = v[1] if len(v) >= 2 else v[0]
            L_b = v[2] if len(v) >= 3 else 0.0
            L_main, x_ini_main = L_b + L_e + L_c + L_e + L_b, L
            suportes_loc = [
                [L_b,                   "pin"],
                [L_b + L_e,             "mov"],
                [L_b + L_e + L_c,       "mov"],
                [L_b + L_e + L_c + L_e, "mov"],
            ]
            tem_balanco = True

        else:
            raise ValueError(f"Tipo estrutural não reconhecido: '{tipo}'")

        return {
            "L_total_mm":   L + L_main + L,
            "x_ini_main":   x_ini_main,
            "x_fim_main":   x_ini_main + L_main,
            "suportes_loc": suportes_loc,
            "tem_balanco":  tem_balanco,
        }

    def _extrair_acoes_fem(
        self,
        x_ini_mm: float,
        x_fim_mm: float,
        offset_mm: float = 0.0,
        tol: float = 1.0,
    ) -> tuple[list, list]:
        """
        Converte as ações definidas pelo usuário (em m e kN) para o formato
        exigido pelo solver FEM (coordenadas locais em mm, forças em N e N/mm).

        Somente as ações que interceptam o intervalo [x_ini_mm, x_fim_mm] são
        incluídas. Posições são clampadas às extremidades do intervalo.

        Parâmetros
        ----------
        x_ini_mm  : float — início do trecho [mm]
        x_fim_mm  : float — fim do trecho [mm]
        offset_mm : float — deslocamento de origem (coord global → local)
        tol       : float — tolerância de interseção [mm]

        Retorna
        -------
        (conc_loc, dist_loc)
        conc_loc : [[x_local_mm, Fy_N], ...]
        dist_loc : [[xa_local_mm, q_Nmm, xb_local_mm, q_Nmm], ...]
        """
        conc, dist = [], []

        for item in self._acoes_raw.get("Carga Concentrada", []):
            if len(item) < 2:
                continue
            F_N = -float(item[0]) * 1000.0   # kN → N (sinal negativo: carga para baixo)
            for c_mm in [float(c) * 1e3 for c in item[1:]]:
                if x_ini_mm - tol <= c_mm <= x_fim_mm + tol:
                    conc.append([max(x_ini_mm, min(x_fim_mm, c_mm)) - offset_mm, F_N])

        for item in self._acoes_raw.get("Carga Distribuída", []):
            if len(item) < 3:
                continue
            q_Nmm = -float(item[0])          # kN/m → N/mm (|item[0]| kN/m = |item[0]| N/mm)
            xa_mm = float(item[1]) * 1e3
            xb_mm = float(item[2]) * 1e3
            a = max(xa_mm, x_ini_mm)
            b = min(xb_mm, x_fim_mm)
            if b - a >= tol:
                dist.append([a - offset_mm, q_Nmm, b - offset_mm, q_Nmm])

        return conc, dist

    # =========================================================================
    # MONTAGEM DAS TABELAS DE SAÍDA
    # =========================================================================

    def _montar_tabela_reacoes(self) -> list[list]:
        """
        Monta a tabela de reações de apoio.

        Formato: [['Posição [m]', 'Apoio', 'R [kN]'], [x_m, 'A', R_kN], ...]
        """
        cab = [["Posição [m]", "Apoio", "R [kN]"]]
        for x_mm in sorted(self._labels_apoio.keys()):
            cab.append([
                round(x_mm / 1000.0, 6),
                self._labels_apoio[x_mm],
                round(self._reacoes.get(x_mm, 0.0) / 1000.0, 6),
            ])
        return cab

    def _montar_tabela_cortante(self) -> list[list]:
        """
        Monta a tabela de esforço cortante com espaçamento de 50 mm.

        Em posições com descontinuidade (apoios, forças concentradas), insere
        duas linhas ('esq.' e 'dir.') somente quando os valores diferem.
        Caso contrário, insere uma única linha com o valor.

        Formato: [['Posição [m]', 'Seção', 'V [kN]'], ...]
        """
        cab  = [["Posição [m]", "Seção", "V [kN]"]]
        d    = self._cortante
        x_mm = 0.0
        TOL  = 1e-6

        while x_mm <= self._L_total_mm + 1e-3:
            x_m  = round(x_mm / 1000.0, 6)
            base = f"{x_mm:.3f}"
            ke, kd = base + 'e', base + 'd'

            if ke in d and kd in d:
                v_e = float(d[ke])
                v_d = float(d[kd])
                if abs(v_e - v_d) < TOL:
                    cab.append([x_m, f"({x_m:.2f} m)", round(v_e, 6)])
                else:
                    cab.append([x_m, f"({x_m:.2f} m) esq.", round(v_e, 6)])
                    cab.append([x_m, f"({x_m:.2f} m) dir.", round(v_d, 6)])
            else:
                val = self._interpolar_cortante(x_mm)
                cab.append([x_m, f"({x_m:.2f} m)", round(val, 6)])

            x_mm += 50.0

        return cab

    def _montar_tabela_momento(self) -> list[list]:
        """
        Monta a tabela de momento fletor com espaçamento de 50 mm.

        Formato: [['Posição [m]', 'Seção', 'M [kNm]'], ...]
        """
        cab  = [["Posição [m]", "Seção", "M [kNm]"]]
        x_mm = 0.0
        while x_mm <= self._L_total_mm + 1e-3:
            x_m = round(x_mm / 1000.0, 6)
            cab.append([x_m, f"({x_m:.2f} m)", round(self._interpolar_momento(x_mm), 6)])
            x_mm += 50.0
        return cab

    # =========================================================================
    # INTERPOLAÇÃO DE VALORES INTERMEDIÁRIOS
    # =========================================================================

    def _interpolar_cortante(self, x_mm: float) -> float:
        """
        Retorna V(x_mm) considerando possíveis descontinuidades.

        Em caso de salto, retorna o valor de maior magnitude (critério conservador).
        """
        d, base = self._cortante, f"{x_mm:.3f}"
        ke, kd  = base + 'e', base + 'd'
        if ke in d and kd in d:
            ve, vd = float(d[ke]), float(d[kd])
            return vd if abs(vd) >= abs(ve) else ve
        for key in (kd, ke, base):
            if key in d:
                return float(d[key])
        return self._interpolar_dict_linear(d, x_mm)

    def _interpolar_momento(self, x_mm: float) -> float:
        """Retorna M(x_mm) por interpolação linear no dicionário de momento."""
        d, key = self._momento, f"{x_mm:.3f}"
        if key in d:
            return float(d[key])
        return self._interpolar_dict_linear(d, x_mm)

    @staticmethod
    def _interpolar_dict_linear(d: dict, x: float) -> float:
        """
        Interpolação linear genérica sobre um dicionário {chave_str: valor}.

        Chaves podem ter sufixos 'e'/'d' (descontinuidades); o valor numérico
        base é extraído por rstrip('ed').
        """
        if not d:
            return 0.0
        xs = sorted(float(k.rstrip('ed')) for k in d)
        if x <= xs[0]:
            return float(list(d.values())[0])
        if x >= xs[-1]:
            return float(list(d.values())[-1])
        for i in range(len(xs) - 1):
            x0, x1 = xs[i], xs[i + 1]
            if x0 <= x <= x1:
                t  = (x - x0) / (x1 - x0) if x1 != x0 else 0.0
                k0 = f"{x0:.3f}"
                k1 = f"{x1:.3f}"
                v0 = d.get(k0, d.get(k0 + 'd', d.get(k0 + 'e', 0.0)))
                v1 = d.get(k1, d.get(k1 + 'e', d.get(k1 + 'd', 0.0)))
                return float(v0) + t * (float(v1) - float(v0))
        return 0.0

    @staticmethod
    def _reacao_em(reac_y: dict, x_mm: float, tol: float = 1.5) -> float:
        """
        Busca a reação vertical no ponto x_mm com tolerância posicional.

        Parâmetros
        ----------
        reac_y : dict {x_mm: R_N}
        x_mm   : float — posição de interesse
        tol    : float — tolerância em mm (padrão 1.5 mm)

        Retorna
        -------
        float — reação em N (0.0 se não encontrada)
        """
        if x_mm in reac_y:
            return float(reac_y[x_mm])
        for k, v in reac_y.items():
            if abs(float(k) - x_mm) <= tol:
                return float(v)
        return 0.0

    def _acumular_reacao(self, x_mm: float, R_N: float):
        """
        Acumula reações de apoio para suportar múltiplas contribuições
        (p. ex., laje + vão principal no mesmo nó de extremidade).
        """
        self._reacoes[x_mm] = self._reacoes.get(x_mm, 0.0) + R_N

    @staticmethod
    def _agregar_diagramas(
        sh_local: dict,
        mo_local: dict,
        offset_mm: float,
        sh_global: dict,
        mo_global: dict,
    ):
        """
        Translada os diagramas locais para o sistema de coordenadas global,
        preservando descontinuidades nos nós de transição entre tramos.

        Lógica especial de prevenção de sobrescrita:
            No início de um novo tramo (x_local = 0), o cortante à esquerda
            ('e') é zero antes de qualquer reação. Se já existe um valor no
            dicionário global para essa seção (vindo do fim do tramo anterior),
            este é preservado e o zero local ignorado.

        Parâmetros
        ----------
        sh_local  : dict — cortante em coordenadas locais
        mo_local  : dict — momento em coordenadas locais
        offset_mm : float — posição global de início do tramo [mm]
        sh_global : dict — dicionário global de cortante (modificado in-place)
        mo_global : dict — dicionário global de momento (modificado in-place)
        """
        for k, v in sh_local.items():
            suf       = k[-1] if k and k[-1] in ('e', 'd') else ''
            x_local   = float(k.rstrip('ed'))
            chave_global = f"{x_local + offset_mm:.3f}{suf}"

            # Preserva valor existente no nó de junção (salto real, não zero artificial)
            if suf == 'e' and abs(x_local) < 1e-6 and chave_global in sh_global:
                continue
            sh_global[chave_global] = v

        for k, v in mo_local.items():
            mo_global[f"{float(k.rstrip('ed')) + offset_mm:.3f}"] = v

    # =========================================================================
    # PLOTAGEM DOS DIAGRAMAS
    # =========================================================================

    def _plotar_diagrama(
        self,
        titulo: str,
        ylabel: str,
        dados: dict,
        inverter_y: bool = False,
    ) -> Figure:
        """
        Gera a figura Matplotlib do diagrama de esforço (cortante ou momento)
        com as seguintes características:
          • Tema escuro (fundo #1e1e1e, painéis #2d2d2d)
          • Curva colorida por sinal: verde (#81c784) para positivo,
            vermelho (#e57373) para negativo
          • Inserção automática de zeros exatos nas transições de sinal
          • Anotações FTool-like nos pontos críticos: linha tracejada + ponto + valor
          • Linhas verticais pontilhadas nos apoios
          • Legenda e dados de interatividade embutidos em fig.interactive_data

        Parâmetros
        ----------
        titulo    : str  — título do gráfico
        ylabel    : str  — rótulo do eixo Y
        dados     : dict — dicionário de esforços (shear_dict ou moment_dict)
        inverter_y: bool — se True inverte o eixo Y (convenção de momento fletor)

        Retorna
        -------
        fig : matplotlib.figure.Figure
        """
        cor_pos = "#81c784"   # Verde — valores positivos
        cor_neg = "#e57373"   # Vermelho — valores negativos

        def _sort_key(k: str):
            """Ordena chaves: pelo valor numérico, depois 'e' < '' < 'd'."""
            suf = k[-1] if k and k[-1] in ('e', 'd') else ''
            return float(k.rstrip('ed')), {'e': 0, '': 1, 'd': 2}.get(suf, 1)

        sorted_keys = sorted(dados.keys(), key=_sort_key)
        X_mm_orig   = np.array([float(k.rstrip('ed')) for k in sorted_keys], dtype=float)
        Y_orig      = np.array([float(dados[k])       for k in sorted_keys], dtype=float)

        # ── Figura vazia para dados insuficientes ─────────────────────────────
        if len(X_mm_orig) == 0:
            fig, ax = plt.subplots(figsize=(9.61, 5.71), dpi=100)
            fig.patch.set_facecolor('#2d2d2d')
            ax.set_facecolor('#1e1e1e')
            fig.interactive_data = None
            return fig

        X_m_orig = X_mm_orig / 1000.0
        X_fino   = np.arange(X_m_orig[0], X_m_orig[-1] + 0.025, 0.05)
        Y_fino   = np.interp(X_fino, X_m_orig, Y_orig)

        # ── Inserir zeros exatos nas transições de sinal ──────────────────────
        sign_ch = np.where(np.diff(np.sign(Y_fino)))[0]
        x_zeros = []
        for i in sign_ch:
            if Y_fino[i + 1] != Y_fino[i]:
                t = -Y_fino[i] / (Y_fino[i + 1] - Y_fino[i])
                x_zeros.append(float(X_fino[i] + t * (X_fino[i + 1] - X_fino[i])))
        if x_zeros:
            ins_idx = np.searchsorted(X_fino, x_zeros)
            X_fino  = np.insert(X_fino, ins_idx, x_zeros)
            Y_fino  = np.insert(Y_fino, ins_idx, np.zeros(len(x_zeros)))

        # ── Configuração do tema escuro ───────────────────────────────────────
        fig, ax = plt.subplots(figsize=(9.61, 5.71), dpi=100)
        fig.patch.set_facecolor('#2d2d2d')
        ax.set_facecolor('#1e1e1e')
        for spine in ax.spines.values():
            spine.set_color('#888888')
        ax.tick_params(colors='white')
        ax.xaxis.label.set_color('white')
        ax.yaxis.label.set_color('white')

        # ── Curva colorida por sinal (LineCollection segmentada) ──────────────
        pts      = np.array([X_fino, Y_fino]).T.reshape(-1, 1, 2)
        segs     = np.concatenate([pts[:-1], pts[1:]], axis=1)
        mid_y    = (Y_fino[:-1] + Y_fino[1:]) / 2.0
        seg_cols = [cor_pos if y >= 0 else cor_neg for y in mid_y]
        lc       = LineCollection(segs, colors=seg_cols, linewidth=2.2, zorder=4)
        ax.add_collection(lc)
        ax.autoscale_view()
        ax.axhline(0, color="#cccccc", linewidth=1.2, zorder=3)

        # ── Detecção de pontos críticos (apoios + extremos locais por vão) ────
        apoios_mm = sorted(self._labels_apoio.keys())
        apoios_m  = [x / 1000.0 for x in apoios_mm]
        y_range   = max(float(np.max(np.abs(Y_orig))), 1e-9)
        threshold = 0.005 * y_range    # ignora < 0,5 % do range global

        criticos:    list = []
        seen_disc:   set  = set()

        # 1) Apoios: com ou sem descontinuidade
        for x_mm in apoios_mm:
            x_m  = x_mm / 1000.0
            base = f"{x_mm:.3f}"
            ke, kd = base + 'e', base + 'd'
            if ke in dados and kd in dados:
                y_e, y_d = float(dados[ke]), float(dados[kd])
                if abs(y_e) > threshold:
                    criticos.append((x_m, y_e, 'e'))
                if abs(y_d) > threshold:
                    criticos.append((x_m, y_d, 'd'))
                seen_disc.add(round(x_mm, 3))
            else:
                y_val = float(np.interp(x_m, X_m_orig, Y_orig))
                if abs(y_val) > threshold:
                    criticos.append((x_m, y_val, ''))

        # 2) Descontinuidades fora dos apoios
        for k in sorted_keys:
            if k.endswith('e') or k.endswith('d'):
                x_mm_d = round(float(k.rstrip('ed')), 3)
                if x_mm_d not in seen_disc:
                    ke2, kd2 = f"{x_mm_d:.3f}e", f"{x_mm_d:.3f}d"
                    x_m_d = x_mm_d / 1000.0
                    if ke2 in dados and kd2 in dados:
                        y_e2, y_d2 = float(dados[ke2]), float(dados[kd2])
                        if abs(y_e2) > threshold:
                            criticos.append((x_m_d, y_e2, 'e'))
                        if abs(y_d2) > threshold:
                            criticos.append((x_m_d, y_d2, 'd'))
                        seen_disc.add(x_mm_d)

        # 3) Extremos locais (pico positivo e negativo entre apoios consecutivos)
        for i in range(len(apoios_m) - 1):
            xa, xb = apoios_m[i], apoios_m[i + 1]
            mask   = (X_m_orig >= xa - 1e-6) & (X_m_orig <= xb + 1e-6)
            if not np.any(mask):
                continue
            x_sub, y_sub = X_m_orig[mask], Y_orig[mask]
            for idx_p in set([int(np.argmax(y_sub)), int(np.argmin(y_sub))]):
                y_p  = y_sub[idx_p]
                x_p  = x_sub[idx_p]
                near = any(abs(x_p - xa_) < 0.05 for xa_ in apoios_m)
                if abs(y_p) > threshold and not near:
                    criticos.append((x_p, y_p, ''))

        # ── Anotação FTool-like: linha tracejada + ponto + label ──────────────
        def _anotar_critico(x_val: float, y_val: float, sufixo: str):
            """Plota linha de referência, marcador e texto de valor crítico."""
            cor = cor_pos if y_val >= 0 else cor_neg
            ax.plot([x_val, x_val], [0.0, y_val],
                    color=cor, linewidth=0.85, linestyle='--', alpha=0.80, zorder=5)
            ax.scatter([x_val], [y_val], s=22, color=cor, zorder=6, linewidths=0)
            tip_is_up = (y_val >= 0) != inverter_y
            va_dir    = 'bottom' if tip_is_up else 'top'
            pad_y     = 3 if tip_is_up else -3
            if sufixo == 'e':
                ha, x_off = 'right', -4
            elif sufixo == 'd':
                ha, x_off = 'left', 4
            else:
                ha, x_off = 'center', 0
            ax.annotate(
                f"{y_val:+.2f}",
                xy=(x_val, y_val), xytext=(x_off, pad_y),
                textcoords="offset points",
                fontsize=7, color=cor, ha=ha, va=va_dir, zorder=8,
            )

        for (xv, yv, suf) in criticos:
            _anotar_critico(xv, yv, suf)

        # ── Linhas verticais nos apoios ───────────────────────────────────────
        for x_mm_ap in self._labels_apoio:
            ax.axvline(
                x_mm_ap / 1000.0, color="#78909C",
                linewidth=0.8, linestyle=":", alpha=0.6, zorder=2,
            )

        # ── Dados de interatividade (hover) ───────────────────────────────────
        _xs_sec, _ys_sec, _lbls, _x_mm2 = [], [], [], 0.0
        while _x_mm2 <= self._L_total_mm + 1e-3:
            _xm2 = _x_mm2 / 1000.0
            _xs_sec.append(_xm2)
            _ys_sec.append(float(np.interp(_xm2, X_m_orig, Y_orig)))
            _lbls.append(f"({_xm2:.2f} m)".replace('.', ','))
            _x_mm2 += 50.0

        ax.set_xlabel("Posição [m]", fontsize=11)
        ax.set_ylabel(ylabel, fontsize=11)
        ax.grid(True, alpha=0.25, linestyle="--", color="#aaaaaa")
        ax.set_xlim(
            -0.01 * self._L_total_mm / 1000.0,
             1.01 * self._L_total_mm / 1000.0,
        )
        if inverter_y:
            ax.invert_yaxis()

        legend = ax.legend(
            handles=[
                mpatches.Patch(color=cor_pos, label="Positivo"),
                mpatches.Patch(color=cor_neg, label="Negativo"),
            ],
            fontsize=9, loc="best", framealpha=0.9,
        )
        legend.get_frame().set_facecolor('#2d2d2d')
        legend.get_frame().set_edgecolor('#888888')
        for text in legend.get_texts():
            text.set_color('white')
        fig.tight_layout()

        # Metadados para interatividade (usado por ativar_interatividade_simples)
        fig.interactive_data = {
            'ax':        ax,
            'xs_secoes': np.array(_xs_sec),
            'ys_secoes': np.array(_ys_sec),
            'labels':    _lbls,
            'ylabel':    ylabel,
            'inverted':  inverter_y,
        }
        return fig

    # =========================================================================
    # SEÇÕES CRÍTICAS (PARA RELATÓRIO)
    # =========================================================================

    def _secoes_criticas(self, tabela: list[list], tipo_nome: str) -> dict:
        """
        Identifica os valores máximo e mínimo na tabela de resultados.

        Parâmetros
        ----------
        tabela    : list[list] — tabela com cabeçalho na linha 0
        tipo_nome : str — nome do esforço para organização do retorno

        Retorna
        -------
        dict com chaves 'Máximo' e 'Mínimo', cada uma contendo
        (posição_str, valor, valor).
        """
        if len(tabela) < 2:
            return {}
        dados     = tabela[1:]
        idx_valor = 2 if len(tabela[0]) == 3 else 1
        lnh_max   = dados[max(range(len(dados)), key=lambda i: float(dados[i][idx_valor]))]
        lnh_min   = dados[min(range(len(dados)), key=lambda i: float(dados[i][idx_valor]))]
        return {
            "Máximo": (f"({float(lnh_max[0]):.2f} m)",
                       round(float(lnh_max[idx_valor]), 4),
                       round(float(lnh_max[idx_valor]), 4)),
            "Mínimo": (f"({float(lnh_min[0]):.2f} m)",
                       round(float(lnh_min[idx_valor]), 4),
                       round(float(lnh_min[idx_valor]), 4)),
        }

    # =========================================================================
    # UTILITÁRIOS
    # =========================================================================

    def _verificar_calculado(self):
        """Garante que calcular() foi chamado antes de acessar resultados."""
        if not self._calculado:
            raise RuntimeError("Análise não executada. Chame calcular() primeiro.")

    @staticmethod
    def _resolver_tipo(tipo_str: str) -> str:
        """
        Traduz a string da interface gráfica para o identificador interno.

        Realiza correspondência direta pelo dicionário _MAPA_TIPOS e,
        se não encontrar, aplica heurística por substrings.
        """
        if tipo_str in _MAPA_TIPOS:
            return _MAPA_TIPOS[tipo_str]
        tl = tipo_str.lower()
        if "balan" in tl:
            return "hiperestatica_com_balanco" if ("hiper" in tl or "contin" in tl) \
                   else "isostatica_em_balanco"
        if "hiper" in tl or "contin" in tl:
            return "hiperestatica_sem_balanco"
        return "biapoiada"


# =============================================================================
# BLOCO 4 — INTERATIVIDADE DOS DIAGRAMAS
# =============================================================================

def ativar_interatividade_simples(fig: Figure, canvas) -> None:
    """
    Conecta callbacks de mouse ao canvas Matplotlib para interatividade
    nos diagramas de esforço.

    Funcionalidades ativadas
    ------------------------
    • Hover (motion_notify_event):
        Linha vertical, ponto destacado e tooltip com posição e valor.
    • Scroll (scroll_event):
        Zoom no eixo Y centralizado na posição do cursor.
    • Duplo clique (button_press_event):
        Restaura os limites originais do eixo Y.

    Parâmetros
    ----------
    fig    : Figure — figura retornada por plotar_cortante() ou plotar_momento()
    canvas : FigureCanvas — canvas Tk/Qt associado à figura
    """
    data = getattr(fig, 'interactive_data', None)
    if data is None:
        return

    ax       = data['ax']
    xs_sec   = data['xs_secoes']
    ys_sec   = data['ys_secoes']
    ylabel   = data['ylabel']
    y_lo_orig, y_hi_orig = ax.get_ylim()

    # Elementos visuais do tooltip (inicialmente invisíveis)
    vline, = ax.plot([], [], color='#FFA726', lw=0.9, linestyle='--', alpha=0.0, zorder=8)
    dot,   = ax.plot([], [], marker='o', markersize=8, color='#A5D6A7',
                     alpha=0.0, zorder=9, linestyle='none')
    tooltip = ax.text(
        0.018, 0.975, '',
        transform=ax.transAxes, fontsize=8.0, color='white',
        va='top', ha='left', linespacing=1.65,
        bbox=dict(boxstyle='round,pad=0.50', facecolor='#0d0d1a',
                  edgecolor='#FFA726', linewidth=0.9, alpha=0.0),
        zorder=20, visible=False,
    )

    def on_move(event):
        """Atualiza tooltip ao mover o cursor sobre o diagrama."""
        if event.inaxes is not ax or event.xdata is None:
            vline.set_alpha(0.0)
            dot.set_alpha(0.0)
            tooltip.set_visible(False)
            canvas.draw_idle()
            return
        idx    = int(np.argmin(np.abs(xs_sec - event.xdata)))
        x_sec  = float(xs_sec[idx])
        y_sec  = float(ys_sec[idx])
        vline.set_data([x_sec, x_sec], ax.get_ylim())
        vline.set_alpha(0.55)
        dot.set_data([x_sec], [y_sec])
        dot.set_color('#A5D6A7' if y_sec >= 0 else '#EF9A9A')
        dot.set_alpha(0.92)
        tooltip.set_text(
            f"  Posição: {x_sec:.2f} m\n  {ylabel} = {y_sec:+.3f}".replace('.', ',')
        )
        tooltip.get_bbox_patch().set_alpha(0.93)
        tooltip.set_visible(True)
        canvas.draw_idle()

    def on_scroll(event):
        """Aplica zoom no eixo Y ao rolar o scroll do mouse."""
        if event.inaxes is not ax:
            return
        y_lo, y_hi = ax.get_ylim()
        y_c   = float(event.ydata) if event.ydata is not None else (y_lo + y_hi) / 2.0
        fator = 0.85 if event.button == 'up' else (1.0 / 0.85)
        ax.set_ylim(y_c - (y_c - y_lo) * fator, y_c + (y_hi - y_c) * fator)
        canvas.draw_idle()

    def on_click(event):
        """Restaura zoom ao dar duplo clique."""
        if event.inaxes is ax and event.dblclick:
            ax.set_ylim(y_lo_orig, y_hi_orig)
            canvas.draw_idle()

    canvas.mpl_connect('motion_notify_event', on_move)
    canvas.mpl_connect('scroll_event',        on_scroll)
    canvas.mpl_connect('button_press_event',  on_click)
