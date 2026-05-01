# =============================================================================
# Calculadora_Gradiente_Termico.py
# =============================================================================
# Módulo autossuficiente para análise de gradiente térmico em estruturas
# hiperestáticas de pontes (vigas contínuas), utilizando o Método dos
# Elementos Finitos (MEF/FEM) adaptado para carregamentos térmicos.
#
# ─── FUNCIONALIDADES ─────────────────────────────────────────────────────────
#   • Cálculo de reações de apoio, esforço cortante e momento fletor
#     induzidos por gradiente de temperatura (ΔT) ao longo da altura da seção.
#   • Suporte a estruturas hiperestáticas com ou sem balanços laterais.
#   • Inclusão opcional de lajes de transição (com esforços nulos).
#   • Geração de tabelas formatadas para exportação.
#   • Plotagem de diagramas com tema escuro e interatividade (hover + scroll).
#
# ─── UNIDADES INTERNAS ───────────────────────────────────────────────────────
#   Comprimento : mm
#   Força       : N  →  saídas convertidas para kN
#   Momento     : N·mm  →  saídas convertidas para kN·m
#   E           : N/mm²  (entrada direta em N/mm² = MPa)
#   Inércia I   : mm⁴   (entrada em cm⁴, convertida internamente)
#   Área A      : mm²   (entrada em cm², convertida internamente)
#   alpha       : 1/°C
#   h           : mm    (altura da seção transversal)
#   ΔT_grad     : °C    (diferença de temperatura topo–base)
#   ΔT_avg      : °C    (variação de temperatura uniforme, normalmente 0)
#
# ─── CONVENÇÃO DE SINAIS ─────────────────────────────────────────────────────
#   Axial   : tração positiva
#   Cortante: positivo quando a face esquerda sobe em relação à direita
#   Momento : positivo quando traciona fibras inferiores (sagging)
#   ΔT_grad : positivo quando o topo está mais quente que a base
#               → induz curvatura convex-up → momento negativo (hogging) em
#                 estrutura livre; hiperestasia gera momentos restritivos.
# =============================================================================

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
from matplotlib.collections import LineCollection
from typing import List, Sequence, Union, Optional

Number = Union[int, float]


# =============================================================================
# BLOCO 1 — MOTOR DE ELEMENTOS FINITOS TÉRMICO (FEM THERMAL)
# Funções de baixo nível: rigidez, cargas térmicas equivalentes, montagem,
# solução e pós-processamento.
# Originalmente em: modules/Elementos_Finitos_Temperatura.py
# =============================================================================

def numeric_element_stiffness(I, E, A, L, theta_deg):
    """
    Calcula e retorna a matriz de rigidez global (6×6), local (6×6) e a
    matriz de transformação (6×6) de um elemento de viga de Bernoulli‑Euler.

    A formulação inclui rigidez axial (EA/L) e rigidez à flexão (baseada em
    EI), sendo a matriz local transformada para coordenadas globais via:
        K_global = Tᵀ · K_local · T

    Parâmetros
    ----------
    I         : float — inércia à flexão [mm⁴]
    E         : float — módulo de elasticidade [N/mm²]
    A         : float — área da seção transversal [mm²]
    L         : float — comprimento do elemento [mm]
    theta_deg : float — inclinação do elemento em relação à horizontal [°]

    Retorna
    -------
    Ke_global : np.ndarray (6×6) — rigidez em coordenadas globais
    Ke_local  : np.ndarray (6×6) — rigidez em coordenadas locais
    T_matrix  : np.ndarray (6×6) — matriz de transformação global→local
    """
    theta = np.radians(theta_deg)
    c, s  = np.cos(theta), np.sin(theta)

    # ── Matriz de rigidez local: [Fx1, Fy1, M1, Fx2, Fy2, M2] ───────────────
    Ke_local = np.array([
        [ E*A/L,            0,           0, -E*A/L,            0,           0],
        [     0,  12*E*I/L**3,  6*E*I/L**2,      0, -12*E*I/L**3,  6*E*I/L**2],
        [     0,   6*E*I/L**2,    4*E*I/L,      0,  -6*E*I/L**2,    2*E*I/L],
        [-E*A/L,            0,           0,  E*A/L,            0,           0],
        [     0, -12*E*I/L**3, -6*E*I/L**2,      0,  12*E*I/L**3, -6*E*I/L**2],
        [     0,   6*E*I/L**2,    2*E*I/L,      0,  -6*E*I/L**2,    4*E*I/L],
    ])

    # ── Matriz de transformação (global → local) ───────────────────────────────
    T_matrix = np.array([
        [ c,  s, 0,  0,  0, 0],
        [-s,  c, 0,  0,  0, 0],
        [ 0,  0, 1,  0,  0, 0],
        [ 0,  0, 0,  c,  s, 0],
        [ 0,  0, 0, -s,  c, 0],
        [ 0,  0, 0,  0,  0, 1],
    ])

    # ── Rigidez global: K_g = Tᵀ K_l T ────────────────────────────────────────
    Ke_global = T_matrix.T @ Ke_local @ T_matrix
    return Ke_global, Ke_local, T_matrix


def calculate_element_thermal_forces(
    I: float, E: float, A: float, L: float, theta_deg: float,
    alpha: float, h: float, dT_avg: float, dT_grad: float,
):
    """
    Calcula as forças nodais equivalentes de carregamento térmico para
    um elemento de pórtico plano, considerando:

    1. Dilatação uniforme (dT_avg):
       Gera força axial de restrição em situação de engastamento total:
           N_rest = −E · A · α · ΔT_avg    [N] (compressão)

    2. Gradiente linear de temperatura (dT_grad = T_topo − T_base):
       Gera curvatura livre κ_livre = α · ΔT_grad / h.
       Em situação totalmente engastada, surgem momentos restritivos:
           M_rest = E · I · κ_livre = E · I · α · ΔT_grad / h   [N·mm]

       Vetor de restrição local (convecção anti-horária positiva):
           f_rest = [N_rest, 0, −M_rest,  −N_rest, 0, +M_rest]ᵀ

    As forças nodais equivalentes são o oposto das forças de restrição,
    rotacionadas para coordenadas globais:
           f_eq_global = Tᵀ · (−f_rest_local)

    Parâmetros
    ----------
    I, E, A, L, theta_deg : propriedades geométrico-mecânicas do elemento
    alpha     : float — coeficiente de dilatação térmica [1/°C]
    h         : float — altura da seção transversal [mm]
    dT_avg    : float — variação de temperatura média (uniforme) [°C]
    dT_grad   : float — gradiente = T_topo − T_base [°C];
                        positivo → topo mais quente → curvatura convex-up

    Retorna
    -------
    f_eq_global        : np.ndarray (6,) — forças equivalentes em coords globais [N, N·mm]
    f_restritivo_local : np.ndarray (6,) — forças de restrição em coords locais
    """
    # ── Força axial de restrição (dilatação uniforme) ─────────────────────────
    F_axial_rest = -E * A * alpha * dT_avg    # negativo = compressão

    # ── Momento restritivo (gradiente térmico) ─────────────────────────────────
    M_rest_mag = (E * I * alpha * dT_grad / h) if h != 0 else 0.0

    # ── Vetor de restrição local: [Fx1, Fy1, M1, Fx2, Fy2, M2] ──────────────
    f_restritivo_local = np.array([
        -F_axial_rest,    # Fx1: reação axial esquerda
         0.0,             # Fy1: sem cisalhamento térmico em viga reta homogênea
        -M_rest_mag,      # M1 : horário no nó esquerdo (combate levantamento)
         F_axial_rest,    # Fx2: reação axial direita
         0.0,             # Fy2
         M_rest_mag,      # M2 : anti-horário no nó direito
    ])

    # ── Forças equivalentes = oposto das forças de restrição ─────────────────
    f_eq_local = -f_restritivo_local

    # ── Rotação para coordenadas globais ──────────────────────────────────────
    theta = np.radians(theta_deg)
    c, s  = np.cos(theta), np.sin(theta)
    T_matrix = np.array([
        [ c,  s, 0,  0,  0, 0],
        [-s,  c, 0,  0,  0, 0],
        [ 0,  0, 1,  0,  0, 0],
        [ 0,  0, 0,  c,  s, 0],
        [ 0,  0, 0, -s,  c, 0],
        [ 0,  0, 0,  0,  0, 1],
    ])
    f_eq_global = T_matrix.T @ f_eq_local

    return f_eq_global, f_restritivo_local


def find_thermal_props(x_mid: float, thermal_loads: list) -> Optional[tuple]:
    """
    Localiza as propriedades térmicas aplicáveis ao elemento de ponto médio x_mid.

    Percorre a lista de zonas de carregamento térmico e retorna os parâmetros
    da primeira zona que contém x_mid. Zonas não sobrepostas são assumidas.

    Parâmetros
    ----------
    x_mid         : float — posição central do elemento [mm]
    thermal_loads : [[x_ini, x_fim, alpha, h, dT_avg, dT_grad], ...]

    Retorna
    -------
    (alpha, h, dT_avg, dT_grad) ou None se x_mid não pertencer a nenhuma zona.
    """
    if not thermal_loads:
        return None
    for load in thermal_loads:
        x_s, x_e, alpha, h, dt_avg, dt_grad = load
        if min(x_s, x_e) <= x_mid <= max(x_s, x_e):
            return (float(alpha), float(h), float(dt_avg), float(dt_grad))
    return None


def build_nodes_from_inputs(
    supports: Sequence[Sequence],
    section_params: Sequence[Sequence],
    *,
    round_to: Optional[int] = 0,
    as_numpy: bool = False,
    tol: float = 1e-6,
) -> Union[List[Number], np.ndarray]:
    """
    Gera a lista ordenada e sem repetições de coordenadas nodais a partir de
    apoios e seções transversais.

    Diferentemente do motor isotérmico, este módulo não recebe forças
    concentradas como entrada — os únicos geradores de nós são os apoios e
    as extremidades de cada trecho de seção.

    Parâmetros
    ----------
    supports      : [[x_mm, 'tipo'], ...]
    section_params: [[x_ini, x_fim, I, E, A, theta], ...]
    round_to      : int | None — casas decimais de arredondamento
    as_numpy      : bool — True → np.ndarray; False → list
    tol           : float — tolerância de fusão (quando round_to=None)

    Retorna
    -------
    Lista ou array de coordenadas x únicas e ordenadas [mm].
    """
    xs = []

    def _safe_x(entry):
        if entry is None or len(entry) == 0:
            return None
        try:
            return float(entry[0])
        except Exception:
            return None

    for s in supports or []:
        x = _safe_x(s)
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

    if round_to is not None:
        xs_rounded = (np.round(xs).astype(int) if round_to == 0
                      else np.round(xs, round_to))
        uniq = np.unique(xs_rounded)
        out  = uniq.astype(int) if round_to == 0 else uniq
    else:
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


def add_points_from_inputs(supports: list, nodes_x: list) -> list:
    """
    Cria a lista de pontos nodais com condições de contorno de apoio.

    Cada nó: [x, Fx, Fy, M, u, v, rot]
      Strings → incógnitas (a resolver)
      0       → valor prescrito (deslocamento ou força nula conhecida)

    Esta versão não recebe forças concentradas externas — as únicas cargas
    são as forças nodais equivalentes térmicas, adicionadas diretamente ao
    vetor global F durante a montagem em fem_thermal().

    Tipos de apoio
    --------------
    'fix' (engaste)  : u=0, v=0, rot=0
    'pin' (pino)     : u=0, v=0;  rot livre → M=0 pelo FEM
    'mov' (rolete)   : v=0;       u e rot livres → Fx=0, M=0 pelo FEM

    Parâmetros
    ----------
    supports : [[x_mm, tipo], ...]
    nodes_x  : list — coordenadas dos nós (saída de build_nodes_from_inputs)

    Retorna
    -------
    points : list — estrutura nodal com condições de contorno aplicadas
    """
    # 1. Criar nós base com incógnitas simbólicas
    points = []
    for i, x in enumerate(nodes_x, start=1):
        points.append([x, f'Fx{i}', f'Fy{i}', f'M{i}', f'u{i}', f'v{i}', f'rot{i}'])

    # 2. Nós sem apoio: forças externas são zero (sem carga mecânica externa)
    x_supports = {float(s[0]) for s in (supports or [])}
    for p in points:
        if p[0] not in x_supports:
            p[1] = 0   # Fx = 0
            p[2] = 0   # Fy = 0
            p[3] = 0   # M  = 0

    def idx_by_x(xval: float) -> int:
        """Localiza índice do nó com coordenada x mais próxima de xval."""
        for k, p in enumerate(points):
            if abs(p[0] - float(xval)) < 1e-6:
                return k
        return -1

    # 3. Aplicar condições de contorno dos apoios
    for x_sup, sup_type in (supports or []):
        idx = idx_by_x(float(x_sup))
        if idx == -1:
            raise ValueError(f"Apoio em x={x_sup} não encontrado na lista de nós.")

        typ = sup_type.strip().lower()
        if typ == 'fix':       # Engaste: bloqueia u, v e rotação
            points[idx][4] = 0   # u   = 0
            points[idx][5] = 0   # v   = 0
            points[idx][6] = 0   # rot = 0
        elif typ == 'pin':     # Pino: bloqueia u e v; rotação livre
            points[idx][3] = 0   # M = 0
            points[idx][4] = 0   # u = 0
            points[idx][5] = 0   # v = 0
        elif typ == 'mov':     # Rolete: bloqueia apenas v
            points[idx][1] = 0   # Fx = 0
            points[idx][3] = 0   # M  = 0
            points[idx][5] = 0   # v  = 0
        else:
            raise ValueError(
                f"Tipo de apoio desconhecido: '{sup_type}'. Use 'fix', 'pin' ou 'mov'."
            )

    return points


def boundary_conditions(points: list) -> tuple:
    """
    Extrai os vetores globais de forças (F) e deslocamentos (U) da lista nodal.

    F = [Fx1, Fy1, M1, Fx2, Fy2, M2, ...]   (3 entradas por nó)
    U = [u1,  v1,  rot1, u2, v2,  rot2, ...]

    Parâmetros
    ----------
    points : lista de nós

    Retorna
    -------
    F : np.ndarray[object]
    U : np.ndarray[object]
    """
    F = np.array([val for p in points for val in p[1:4]], dtype=object)
    U = np.array([val for p in points for val in p[4:7]], dtype=object)
    return F, U


def elements_generator_with_sections(points: list, section_params: list) -> tuple:
    """
    Gera a lista de elementos finitos e o total de GDLs.

    Cada elemento: [I, E, A, L, theta_deg, dof1...dof6]
    Seção determinada pelo ponto médio do elemento.

    Parâmetros
    ----------
    points        : lista de nós
    section_params: [[x_ini, x_fim, I, E, A, theta_deg], ...]

    Retorna
    -------
    elements  : list
    total_dof : int
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
    matrizes elementares empacotadas.

    Formato de Ke empacotada (7×7):
        Ke[0, 1:] = índices globais dos DOFs (base 1)
        Ke[1:, 1:] = submatriz de rigidez 6×6

    Parâmetros
    ----------
    K_elements : list[np.ndarray (7×7)]
    total_dof  : int

    Retorna
    -------
    K_global : np.ndarray (total_dof × total_dof)
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
    Resolve K_global · U = F_global com condições de Dirichlet homogêneas.

    Partição do sistema:
        K_rr · U_r = F_r − K_rf · U_f   (U_f = 0 nos apoios)

    Reações: R = K · U − F   (não nulas apenas nos DOFs fixos)

    Parâmetros
    ----------
    K_global  : np.ndarray (n×n)
    F_global  : np.ndarray (n,)  — inclui contribuição térmica equivalente
    fixed_dofs: list[int]

    Retorna
    -------
    U_full : np.ndarray (n,) — deslocamentos e rotações
    R      : np.ndarray (n,) — reações
    """
    total_dof = K_global.shape[0]
    free_dofs = [i for i in range(total_dof) if i not in fixed_dofs]

    K_rr = K_global[np.ix_(free_dofs, free_dofs)]
    K_rf = K_global[np.ix_(free_dofs, fixed_dofs)]
    F_r  = F_global[free_dofs]
    U_f  = np.zeros(len(fixed_dofs))

    try:
        U_r = np.linalg.solve(K_rr, F_r - K_rf @ U_f)
    except np.linalg.LinAlgError:
        raise np.linalg.LinAlgError(
            "Matriz de rigidez singular. Verifique se a estrutura está "
            "adequadamente restringida (número e tipo de apoios)."
        )

    U_full = np.zeros(total_dof)
    U_full[free_dofs]  = U_r
    U_full[fixed_dofs] = U_f

    R = K_global @ U_full - F_global
    return U_full, R


def fem_thermal(
    supports: list,
    section_params: list,
    thermal_loads: list,
) -> tuple:
    """
    Orquestrador principal do Motor de Elementos Finitos para cargas TÉRMICAS.

    Executa o pipeline completo:
        1. Geração automática de nós (apoios + extremos de seção)
        2. Montagem da estrutura nodal com condições de contorno
        3. Extração dos vetores F (externo = 0) e U
        4. Geração dos elementos com propriedades de seção
        5. Cálculo de rigidez e forças térmicas equivalentes por elemento
        6. Montagem da matriz de rigidez global
        7. Identificação dos DOFs fixos
        8. Solução do sistema linear (K · U = F_térmico)

    Parâmetros
    ----------
    supports      : [[x_mm, tipo], ...]
                    Tipos: 'fix', 'pin', 'mov'
    section_params: [[x_ini, x_fim, I_mm4, E_Nmm2, A_mm2, theta_deg], ...]
    thermal_loads : [[x_ini, x_fim, alpha, h_mm, dT_avg, dT_grad], ...]
                    Zonas de carregamento térmico (podem ser múltiplas)

    Retorna
    -------
    U_full       : np.ndarray — deslocamentos e rotações nodais [mm, rad]
    R            : np.ndarray — reações em todos os GDLs [N, N·mm]
    nodes_x      : list       — coordenadas X dos nós [mm]
    elements     : list       — lista de elementos gerados
    element_data : list       — [(Ke_local, T_matrix, f_restritivo_local), ...]
    """
    # 1. Construir nós (apoios + extremos de seção)
    nodes_x = build_nodes_from_inputs(supports, section_params)

    # 2. Estrutura nodal com condições de contorno
    points = add_points_from_inputs(supports, nodes_x)

    # 3. Vetores F (externo) e U
    F, U = boundary_conditions(points)

    # 4. Gerar elementos e número total de GDLs
    elements, total_dof = elements_generator_with_sections(points, section_params)

    # 5. Calcular matrizes de rigidez e forças térmicas equivalentes por elemento
    K_elements_packed = []
    element_data      = []
    F_thermal_global  = np.zeros(total_dof)

    for i, el in enumerate(elements):
        I, E, A, L, theta, *dofs_1based = el

        x_left  = float(points[i][0])
        x_right = float(points[i + 1][0])
        x_mid   = 0.5 * (x_left + x_right)

        # Rigidez do elemento (retorna global, local e T)
        Ke_global_i, Ke_local_i, T_i = numeric_element_stiffness(I, E, A, L, theta)

        # Empacotamento para montagem global
        Ke_packed = np.zeros((7, 7))
        Ke_packed[0, 1:]  = dofs_1based
        Ke_packed[1:, 0]  = dofs_1based
        Ke_packed[1:, 1:] = Ke_global_i
        K_elements_packed.append(Ke_packed)

        # Forças térmicas equivalentes
        f_restritivo_local_i = np.zeros(6)
        thermal_props = find_thermal_props(x_mid, thermal_loads)

        if thermal_props:
            alpha, h, dt_avg, dt_grad = thermal_props
            f_eq_global_i, f_res_local_i = calculate_element_thermal_forces(
                I, E, A, L, theta, alpha, h, dt_avg, dt_grad
            )
            f_restritivo_local_i = f_res_local_i
            dofs_0based = [d - 1 for d in dofs_1based]
            for k in range(6):
                F_thermal_global[dofs_0based[k]] += f_eq_global_i[k]

        element_data.append((Ke_local_i, T_i, f_restritivo_local_i))

    # 6. Montar matriz de rigidez global
    K_global = assemble_global_stiffness(K_elements_packed, total_dof)

    # 7. Identificar DOFs fixos
    fixed_dofs = [i for i, val in enumerate(U) if val == 0]

    # 8. Forças externas = 0; forças totais = térmicas equivalentes
    def _to_float(f):
        return float(f) if isinstance(f, (int, float)) else 0.0

    F_externo = np.array([_to_float(f) for f in F], dtype=float)
    F_total   = F_externo + F_thermal_global

    # 9. Resolver
    U_full, R = solve_fem_numeric(K_global, F_total, fixed_dofs)

    return U_full, R, nodes_x, elements, element_data


def calculate_internal_forces(
    U_full: np.ndarray,
    elements: list,
    element_data: list,
    nodes_x: list,
) -> tuple:
    """
    Calcula os esforços internos (axial, cortante, momento) em cada nó,
    incorporando os efeitos de cargas térmicas via f_restritivo_local.

    Para cada elemento i (entre nós i e i+1):
        u_local = T · u_global
        f_local = K_local · u_local + f_restritivo_local

    Os componentes de f_local são:
        f_local[0] = Fx_i → axial esquerdo
        f_local[1] = Fy_i → cortante esquerdo
        f_local[2] = M_i  → momento esquerdo
        f_local[3] = Fx_j → axial direito
        f_local[4] = Fy_j → cortante direito
        f_local[5] = M_j  → momento direito

    Em nós intermediários (entre dois elementos), cada dicionário acumula
    DOIS valores: fim do elemento esquerdo (índice 0) e início do elemento
    direito (índice 1). A diferença entre eles corresponde à reação de apoio.

    Convenção de sinais
    -------------------
    Axial    : tração positiva
    Cortante : positivo quando Fy no início do elemento aponta para cima
    Momento  : positivo quando traciona fibras inferiores (sagging)

    Parâmetros
    ----------
    U_full       : np.ndarray — vetor de deslocamentos
    elements     : list       — lista de elementos
    element_data : list       — [(Ke_local, T_matrix, f_restritivo_local), ...]
    nodes_x      : list       — coordenadas dos nós [mm]

    Retorna
    -------
    shear_results  : dict {x_mm: [V_N, ...]}
    moment_results : dict {x_mm: [M_Nmm, ...]}
    axial_results  : dict {x_mm: [N_N, ...]}
    """
    shear_results  = {x: [] for x in nodes_x}
    moment_results = {x: [] for x in nodes_x}
    axial_results  = {x: [] for x in nodes_x}

    for i, (el, (Ke_local, T_matrix, f_restritivo_local)) in enumerate(
        zip(elements, element_data)
    ):
        dofs_1based = el[5:]
        dofs_0based = [d - 1 for d in dofs_1based]

        # Deslocamentos globais → locais
        u_global = U_full[dofs_0based]
        u_local  = T_matrix @ u_global

        # Forças locais = K_local · u_local + f_restritivo (inclui efeito térmico)
        f_local = Ke_local @ u_local + f_restritivo_local

        Fx_i, Fy_i, M_i = f_local[0], f_local[1], f_local[2]
        Fx_j, Fy_j, M_j = f_local[3], f_local[4], f_local[5]

        x_i = nodes_x[i]
        x_j = nodes_x[i + 1]

        # Nó inicial — esforços saindo do elemento pela esquerda
        axial_results[x_i].append(-Fx_i)
        shear_results[x_i].append(Fy_i)
        moment_results[x_i].append(-M_i)

        # Nó final — esforços chegando no elemento pela direita
        axial_results[x_j].append(Fx_j)
        shear_results[x_j].append(-Fy_j)
        moment_results[x_j].append(M_j)

    return shear_results, moment_results, axial_results


def extract_reactions_fy(
    R: np.ndarray,
    nodes_x: list,
    supports: list,
) -> dict:
    """
    Extrai as reações verticais (Fy) de cada apoio a partir do vetor R.

    O índice global de Fy do nó i é: 3·i + 1  (base 0).

    Parâmetros
    ----------
    R        : np.ndarray — vetor de reações completo (retorno de fem_thermal)
    nodes_x  : list — coordenadas dos nós [mm]
    supports : [[x_mm, tipo], ...] — mesmo formato passado ao fem_thermal

    Retorna
    -------
    dict {x_mm_apoio: R_fy_N}
    """
    reactions  = {}
    nodes_list = list(nodes_x)

    for x_sup, _ in supports:
        x_sup_f = float(x_sup)
        try:
            i_node = nodes_list.index(x_sup_f)
        except ValueError:
            diffs  = [abs(nx - x_sup_f) for nx in nodes_list]
            i_node = int(np.argmin(diffs))
            if diffs[i_node] > 0.5:
                continue

        fy_gdl = 3 * i_node + 1           # GDL de Fy (0-based)
        reactions[x_sup_f] = float(R[fy_gdl])

    return reactions


def build_diagram_dicts(
    nodes_x: list,
    shear_results: dict,
    moment_results: dict,
    x_offset: float = 0.0,
) -> tuple:
    """
    Monta os dicionários de cortante e momento fletor no formato esperado
    pelo método _plotar_diagrama da calculadora.

    Formato das chaves
    ------------------
    Nós de extremidade (1 valor) : "x_glob.3f"
    Nós intermediários (2 valores): "x_glob.3fe"  ← valor do elem. esquerdo
                                    "x_glob.3fd"  ← valor do elem. direito

    Unidades de saída
    -----------------
    Cortante : kN   (entrada em N,   divisão por 1 000)
    Momento  : kN·m (entrada em N·mm, divisão por 1 000 000)

    Parâmetros
    ----------
    nodes_x       : coordenadas dos nós em coordenadas LOCAIS do FEM [mm]
    shear_results : {x_mm: [V_N, ...]}
    moment_results: {x_mm: [M_Nmm, ...]}
    x_offset      : float — translação para coordenadas globais [mm]

    Retorna
    -------
    (cortante_dict, momento_dict)
    """
    cortante_dict = {}
    momento_dict  = {}
    n = len(nodes_x)

    for i, x_loc in enumerate(nodes_x):
        x_glob   = x_loc + x_offset
        key_base = f"{x_glob:.3f}"

        V_list = shear_results.get(x_loc, [0.0])
        M_list = moment_results.get(x_loc, [0.0])

        if len(V_list) == 2:
            # Nó intermediário → descontinuidade de cortante
            cortante_dict[key_base + 'e'] = V_list[0] / 1000.0   # N → kN
            cortante_dict[key_base + 'd'] = V_list[1] / 1000.0
        else:
            # Extremidade → ponto simples
            cortante_dict[key_base] = V_list[0] / 1000.0

        # Momento é contínuo: usa média se existir dois valores
        M_val = float(np.mean(M_list)) / 1e6                      # N·mm → kN·m
        momento_dict[key_base] = M_val

    return cortante_dict, momento_dict


# =============================================================================
# BLOCO 2 — MAPEAMENTO DE TIPOS ESTRUTURAIS
# =============================================================================

# Apenas tipos hiperestáticos são suportados para análise térmica
# (estruturas isostáticas são hiperestáticas: sem restrição às deformações térmicas)
_MAPA_TIPOS: dict[str, str] = {
    "Hiperestática: Vão Contínuo sem Balanço": "hiperestatica_sem_balanco",
    "Hiperestática: Vão Contínuo com Balanço": "hiperestatica_com_balanco",
}


# =============================================================================
# BLOCO 3 — CLASSE PRINCIPAL: CalculadoraGradienteTermico
# =============================================================================

class CalculadoraGradienteTermico:
    """
    Calculadora de esforços induzidos por gradiente térmico em superestruturas
    hiperestáticas de pontes.

    Fundamento teórico
    ------------------
    Em estruturas isostáticas, gradientes térmicos geram deformações livres
    sem produzir esforços internos. Em estruturas hiperestáticas, os vínculos
    impedem a deformação livre, induzindo esforços de restrição.

    Para um gradiente ΔT_grad = T_topo − T_base:
        κ_livre = α · ΔT_grad / h          (curvatura térmica livre)
        M_rest  = E · I · κ_livre           (momento restritivo em engaste total)

    O FEM resolve a estrutura hiperestática sujeita às forças nodais
    equivalentes correspondentes às forças de restrição.

    Parâmetros de Construção
    ------------------------
    superestrutura       : objeto com atributos:
                            .tipo            — string do tipo estrutural
                            .vaos            — list[float], comprimentos [m]
                            .laje_transicao  — float | False | None [m]
    secao_superestrutura : objeto com .parametros_geometricos (dict):
                            'Ix'   — inércia [cm⁴]
                            'Area' — área    [cm²]
                            'h'    — altura  [cm]
    parametros_temperatura : dict com:
                            'E'      — módulo de elasticidade [N/mm²]
                            'alpha'  — coef. dilatação [1/°C]
                            'deltat' — gradiente ΔT [°C]
    """

    def __init__(
        self,
        superestrutura,
        secao_superestrutura,
        parametros_temperatura: dict,
    ):
        self._super    = superestrutura
        self._secao    = secao_superestrutura
        self._params_t = parametros_temperatura
        self._tipo     = self._resolver_tipo(superestrutura.tipo)

        # ── Propriedades geométricas (entrada cm → interno mm) ─────────────────
        pg = secao_superestrutura.parametros_geometricos
        self._Ix_mm4 = float(pg["Ix"])   * 1e4    # cm⁴ → mm⁴
        self._A_mm2  = float(pg["Area"]) * 1e2    # cm² → mm²
        self._h_mm   = float(pg["h"])    * 10.0   # cm  → mm

        # ── Parâmetros térmicos ────────────────────────────────────────────────
        self._E_Nmm2  = float(parametros_temperatura["E"])       # N/mm² (MPa)
        self._alpha   = float(parametros_temperatura["alpha"])   # 1/°C
        self._dT_grad = float(parametros_temperatura["deltat"])  # °C
        self._dT_avg  = 0.0   # variação uniforme (não utilizada neste módulo)

        # ── Geometria em milímetros ────────────────────────────────────────────
        self._vaos_mm: list[float] = [v * 1e3 for v in superestrutura.vaos]
        self._laje_mm: float = 0.0
        if superestrutura.laje_transicao is not False and \
           superestrutura.laje_transicao is not None:
            self._laje_mm = float(superestrutura.laje_transicao) * 1e3

        # ── Resultados internos ────────────────────────────────────────────────
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
        Executa a análise estrutural térmica e retorna as três tabelas.

        Retorna
        -------
        (tabela_reacoes, tabela_cortante, tabela_momento)
        """
        self._analisar_continua_termica()
        self._calculado = True
        return (
            self._montar_tabela_reacoes(),
            self._montar_tabela_cortante(),
            self._montar_tabela_momento(),
        )

    def plotar_cortante(self) -> Figure:
        """Gera e retorna a figura do diagrama de esforço cortante."""
        self._verificar_calculado()
        return self._plotar_diagrama(
            "Diagrama de Esforço Cortante", "V [kN]",
            self._cortante, inverter_y=False,
        )

    def plotar_momento(self) -> Figure:
        """Gera e retorna a figura do diagrama de momento fletor."""
        self._verificar_calculado()
        return self._plotar_diagrama(
            "Diagrama de Momento Fletor", "M [kN·m]",
            self._momento, inverter_y=True,
        )

    # =========================================================================
    # ANÁLISE TÉRMICA — VÃO CONTÍNUO HIPERESTÁTICO
    # =========================================================================

    def _analisar_continua_termica(self):
        """
        Resolve o vão principal hiperestático sob gradiente térmico via FEM.

        Lajes de transição são tratadas como zonas sem carregamento (esforços
        nulos), com descontinuidades de cortante tratadas explicitamente na
        junção com o vão principal.

        Fluxo de execução:
            1. Calcular geometria (vãos e posições de apoio)
            2. Definir parâmetros de seção e carregamento térmico
            3. Resolver via fem_thermal()
            4. Pós-processar esforços internos (calculate_internal_forces)
            5. Montar dicionários de diagrama (build_diagram_dicts)
            6. Preencher zonas de laje com zeros
            7. Tratar descontinuidades de cortante nas junções laje/vão
            8. Extrair e armazenar reações de apoio
        """
        geo = self._calcular_geometria()
        L_main      = geo["L_main_mm"]
        x_ini_main  = geo["x_ini_main"]
        suportes_loc = geo["suportes_loc"]
        L_total     = geo["L_total_mm"]

        # ── Parâmetros do FEM térmico ──────────────────────────────────────────
        section_params = [[0.0, L_main, self._Ix_mm4, self._E_Nmm2, self._A_mm2, 0.0]]
        thermal_loads  = [[0.0, L_main, self._alpha, self._h_mm, self._dT_avg, self._dT_grad]]

        # ── Resolver o sistema ─────────────────────────────────────────────────
        U_full, R_vec, nodes_x, elements, element_data = fem_thermal(
            suportes_loc, section_params, thermal_loads
        )

        # ── Pós-processamento: esforços internos ───────────────────────────────
        shear_results, moment_results, _ = calculate_internal_forces(
            U_full, elements, element_data, nodes_x
        )

        # ── Montar dicionários de diagrama (coordenadas globais) ───────────────
        cortante_main, momento_main = build_diagram_dicts(
            nodes_x, shear_results, moment_results, x_offset=x_ini_main
        )

        # ── Agregar lajes (zeros) ──────────────────────────────────────────────
        cortante_global: dict = {}
        momento_global:  dict = {}

        if self._laje_mm > 0:
            self._preencher_zeros(0.0, self._laje_mm, cortante_global, momento_global)

        cortante_global.update(cortante_main)
        momento_global.update(momento_main)

        if self._laje_mm > 0:
            x_fim_main = x_ini_main + L_main
            self._preencher_zeros(
                x_fim_main, x_fim_main + self._laje_mm,
                cortante_global, momento_global,
            )

        # ── Tratar descontinuidades de cortante nas junções laje/vão ──────────
        # As lajes têm V = 0; o vão principal tem V ≠ 0.
        # Inserir explicitamente saltos nos pontos de transição.
        if self._laje_mm > 0:
            x_fim_main = x_ini_main + L_main

            # Descontinuidade na entrada do vão principal (laje esq. → vão)
            key_ini = f"{x_ini_main:.3f}"
            if key_ini in cortante_global:
                v_main_ini = cortante_global.pop(key_ini)
                cortante_global[key_ini + 'e'] = 0.0           # laje: V = 0
                cortante_global[key_ini + 'd'] = v_main_ini    # vão: V ≠ 0

            # Descontinuidade na saída do vão principal (vão → laje dir.)
            key_fim = f"{x_fim_main:.3f}"
            if key_fim in cortante_global:
                v_main_fim = cortante_global.pop(key_fim)
                cortante_global[key_fim + 'e'] = v_main_fim    # vão: V ≠ 0
                cortante_global[key_fim + 'd'] = 0.0           # laje: V = 0

        self._cortante, self._momento, self._L_total_mm = (
            cortante_global, momento_global, L_total
        )

        # ── Reações de apoio ───────────────────────────────────────────────────
        reacoes_locais = extract_reactions_fy(R_vec, nodes_x, suportes_loc)
        label_idx = 0

        if self._laje_mm > 0:
            # Apoio fictício no início da laje (sem reação real — V = 0)
            self._labels_apoio[0.0] = chr(65 + label_idx)
            self._acumular_reacao(0.0, 0.0)
            label_idx += 1

        for x_loc, _ in sorted(suportes_loc, key=lambda s: s[0]):
            x_glob = round(x_ini_main + float(x_loc), 3)
            self._labels_apoio[x_glob] = chr(65 + label_idx)
            self._acumular_reacao(x_glob, reacoes_locais.get(float(x_loc), 0.0))
            label_idx += 1

        if self._laje_mm > 0:
            x_fim_main = x_ini_main + L_main
            x_ext_dir  = round(x_fim_main + self._laje_mm, 3)
            self._labels_apoio[x_ext_dir] = chr(65 + label_idx)
            self._acumular_reacao(x_ext_dir, 0.0)

    def _calcular_geometria(self) -> dict:
        """
        Determina a geometria do vão principal e a posição dos apoios internos.

        Tipos suportados
        ----------------
        hiperestatica_sem_balanco:
            4 apoios: pin–mov–mov–mov em [0, L_e, L_e+L_c, L_e+L_c+L_e]

        hiperestatica_com_balanco:
            4 apoios internos, com balanços de comprimento L_b em cada extremo:
            pin–mov–mov–mov em [L_b, L_b+L_e, L_b+L_e+L_c, L_b+L_e+L_c+L_e]

        Retorna
        -------
        dict com chaves: 'L_main_mm', 'x_ini_main', 'L_total_mm', 'suportes_loc'
        """
        v, L, tipo = self._vaos_mm, self._laje_mm, self._tipo

        if tipo == "hiperestatica_sem_balanco":
            L_c, L_e = v[0], v[1] if len(v) >= 2 else v[0]
            L_main = L_e + L_c + L_e
            suportes_loc = [
                [0.0,            "pin"],
                [L_e,            "mov"],
                [L_e + L_c,      "mov"],
                [L_e + L_c + L_e,"mov"],
            ]

        elif tipo == "hiperestatica_com_balanco":
            L_c = v[0]
            L_e = v[1] if len(v) >= 2 else v[0]
            L_b = v[2] if len(v) >= 3 else 0.0
            L_main = L_b + L_e + L_c + L_e + L_b
            suportes_loc = [
                [L_b,                   "pin"],
                [L_b + L_e,             "mov"],
                [L_b + L_e + L_c,       "mov"],
                [L_b + L_e + L_c + L_e, "mov"],
            ]

        else:
            raise ValueError(f"Tipo não suportado para análise térmica: '{self._tipo}'")

        return {
            "L_main_mm":   L_main,
            "x_ini_main":  L,
            "L_total_mm":  L + L_main + L,
            "suportes_loc": suportes_loc,
        }

    @staticmethod
    def _preencher_zeros(
        x_ini_mm: float,
        x_fim_mm: float,
        cortante_global: dict,
        momento_global: dict,
        dx_mm: float = 500.0,
    ):
        """
        Preenche as regiões de laje com valores nulos nos dicionários de diagrama.

        Como as lajes de transição não possuem vínculos internos para o
        gradiente térmico do vão principal, seus esforços são zero.

        Parâmetros
        ----------
        x_ini_mm, x_fim_mm : float — intervalo [mm]
        cortante_global, momento_global : dict — modificados in-place
        dx_mm : float — passo de discretização [mm]
        """
        x = x_ini_mm
        while x <= x_fim_mm + 1e-3:
            key = f"{x:.3f}"
            cortante_global.setdefault(key, 0.0)
            momento_global.setdefault(key, 0.0)
            x += dx_mm
        cortante_global.setdefault(f"{x_fim_mm:.3f}", 0.0)
        momento_global.setdefault(f"{x_fim_mm:.3f}", 0.0)

    # =========================================================================
    # MONTAGEM DAS TABELAS DE SAÍDA
    # =========================================================================

    def _montar_tabela_reacoes(self) -> list[list]:
        """Tabela de reações de apoio em kN."""
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
        Tabela de esforço cortante com espaçamento de 50 mm.

        Insere duas linhas em posições com descontinuidade (laje/vão).
        Remove duplicatas exatas via _limpar_duplicatas_tabela().
        """
        cab  = [["Posição [m]", "Seção", "V [kN]"]]
        d    = self._cortante
        x_mm = 0.0
        while x_mm <= self._L_total_mm + 1e-3:
            x_m  = round(x_mm / 1000.0, 6)
            base = f"{x_mm:.3f}"
            ke, kd = base + 'e', base + 'd'
            if ke in d and kd in d:
                cab.append([x_m, f"({x_m:.2f} m) esq.", round(float(d[ke]), 6)])
                cab.append([x_m, f"({x_m:.2f} m) dir.", round(float(d[kd]), 6)])
            else:
                cab.append([x_m, f"({x_m:.2f} m)", round(self._interpolar_cortante(x_mm), 6)])
            x_mm += 50.0
        return self._limpar_duplicatas_tabela(cab)

    def _montar_tabela_momento(self) -> list[list]:
        """Tabela de momento fletor com espaçamento de 50 mm."""
        cab  = [["Posição [m]", "Seção", "M [kNm]"]]
        x_mm = 0.0
        while x_mm <= self._L_total_mm + 1e-3:
            x_m = round(x_mm / 1000.0, 6)
            cab.append([x_m, f"({x_m:.2f} m)", round(self._interpolar_momento(x_mm), 6)])
            x_mm += 50.0
        return cab

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
        Gera a figura Matplotlib do diagrama de esforço com:
          • Tema escuro (fundo #1e1e1e / #2d2d2d)
          • Curva colorida por sinal (verde/vermelho)
          • Zeros exatos nas transições de sinal
          • Anotações FTool-like nos pontos críticos
          • Linhas verticais pontilhadas nos apoios
          • Metadados de interatividade em fig.interactive_data

        Parâmetros
        ----------
        titulo    : str  — título do gráfico
        ylabel    : str  — rótulo do eixo Y
        dados     : dict — dicionário de esforços
        inverter_y: bool — inverte eixo Y (convenção de momento fletor)

        Retorna
        -------
        fig : matplotlib.figure.Figure
        """
        cor_pos = "#81c784"
        cor_neg = "#e57373"

        def _sort_key(k: str):
            suf = k[-1] if k and k[-1] in ('e', 'd') else ''
            return float(k.rstrip('ed')), {'e': 0, '': 1, 'd': 2}.get(suf, 1)

        sorted_keys = sorted(dados.keys(), key=_sort_key)
        X_mm_orig   = np.array([float(k.rstrip('ed')) for k in sorted_keys], dtype=float)
        Y_orig      = np.array([float(dados[k])       for k in sorted_keys], dtype=float)

        if len(X_mm_orig) == 0:
            fig, ax = plt.subplots(figsize=(9.61, 5.71), dpi=100)
            fig.patch.set_facecolor('#2d2d2d')
            ax.set_facecolor('#1e1e1e')
            fig.interactive_data = None
            return fig

        X_m_orig = X_mm_orig / 1000.0
        X_fino   = np.arange(X_m_orig[0], X_m_orig[-1] + 0.025, 0.05)
        Y_fino   = np.interp(X_fino, X_m_orig, Y_orig)

        # ── Zeros exatos nas transições de sinal ──────────────────────────────
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

        # ── Tema escuro ───────────────────────────────────────────────────────
        fig, ax = plt.subplots(figsize=(9.61, 5.71), dpi=100)
        fig.patch.set_facecolor('#2d2d2d')
        ax.set_facecolor('#1e1e1e')
        for spine in ax.spines.values():
            spine.set_color('#888888')
        ax.tick_params(colors='white')
        ax.xaxis.label.set_color('white')
        ax.yaxis.label.set_color('white')

        # ── Curva colorida por sinal ───────────────────────────────────────────
        pts      = np.array([X_fino, Y_fino]).T.reshape(-1, 1, 2)
        segs     = np.concatenate([pts[:-1], pts[1:]], axis=1)
        mid_y    = (Y_fino[:-1] + Y_fino[1:]) / 2.0
        seg_cols = [cor_pos if y >= 0 else cor_neg for y in mid_y]
        lc       = LineCollection(segs, colors=seg_cols, linewidth=2.2, zorder=4)
        ax.add_collection(lc)
        ax.autoscale_view()
        ax.axhline(0, color="#cccccc", linewidth=1.2, zorder=3)

        # ── Detecção de pontos críticos ───────────────────────────────────────
        apoios_mm = sorted(self._labels_apoio.keys())
        apoios_m  = [x / 1000.0 for x in apoios_mm]
        y_range   = max(float(np.max(np.abs(Y_orig))), 1e-9)
        threshold = 0.005 * y_range

        criticos:  list = []
        seen_disc: set  = set()

        # 1) Apoios
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

        # 3) Extremos locais por vão
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

        # ── Anotações FTool-like ───────────────────────────────────────────────
        def _anotar_critico(x_val: float, y_val: float, sufixo: str):
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

        # ── Dados de interatividade (passo de 500 mm para gradiente térmico) ──
        _xs_sec, _ys_sec, _lbls = [], [], []
        _x_mm2, _s_idx2 = 0.0, 1
        while _x_mm2 <= self._L_total_mm + 1e-3:
            _xm2 = _x_mm2 / 1000.0
            _xs_sec.append(_xm2)
            _ys_sec.append(float(np.interp(_xm2, X_m_orig, Y_orig)))
            _lbls.append(f"S{_s_idx2}")
            _x_mm2 += 500.0
            _s_idx2 += 1

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
    # INTERPOLAÇÃO DE VALORES INTERMEDIÁRIOS
    # =========================================================================

    def _interpolar_cortante(self, x_mm: float) -> float:
        """Retorna V(x_mm), priorizando o maior valor em descontinuidades."""
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
        """Retorna M(x_mm) por interpolação linear."""
        d, key = self._momento, f"{x_mm:.3f}"
        if key in d:
            return float(d[key])
        return self._interpolar_dict_linear(d, x_mm)

    @staticmethod
    def _interpolar_dict_linear(d: dict, x: float) -> float:
        """Interpolação linear genérica sobre dicionário com chaves 'x.3f[e|d]'."""
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

    # =========================================================================
    # UTILITÁRIOS
    # =========================================================================

    def _acumular_reacao(self, x_mm: float, R_N: float):
        """Acumula reação de apoio (permite múltiplas contribuições no mesmo nó)."""
        self._reacoes[x_mm] = self._reacoes.get(x_mm, 0.0) + R_N

    def _verificar_calculado(self):
        """Verifica se calcular() já foi executado."""
        if not self._calculado:
            raise RuntimeError("Análise não executada.")

    @staticmethod
    def _resolver_tipo(tipo_str: str) -> str:
        """Traduz a string da interface para o identificador interno."""
        if tipo_str in _MAPA_TIPOS:
            return _MAPA_TIPOS[tipo_str]
        tl = tipo_str.lower()
        if "isostat" in tl or "biapoiad" in tl:
            raise ValueError(
                f"Tipo '{tipo_str}' é isostático e não gera esforços por gradiente térmico."
            )
        if "hiper" in tl or "continu" in tl:
            return ("hiperestatica_com_balanco" if "balan" in tl
                    else "hiperestatica_sem_balanco")
        raise ValueError(f"Tipo estrutural desconhecido: '{tipo_str}'.")

    def _secoes_criticas(self, tabela: list[list], tipo_nome: str) -> dict:
        """Identifica valores máximo e mínimo na tabela de resultados."""
        if len(tabela) < 2:
            return {}
        dados     = tabela[1:]
        idx_valor = 2
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

    @staticmethod
    def _limpar_duplicatas_tabela(tabela: list[list]) -> list[list]:
        """
        Remove linhas duplicadas (mesmo valor) na tabela de cortante.

        Em descontinuidades com V_esq ≈ V_dir (diferença < 1e-6), mantém
        apenas uma linha para evitar redundância visual.
        """
        if len(tabela) < 2:
            return tabela
        agrupado = {}
        for linha in tabela[1:]:
            chave = round(float(linha[0]), 6)
            if chave not in agrupado:
                agrupado[chave] = []
            agrupado[chave].append(linha)

        dados_limpos = []
        for chave in sorted(agrupado.keys()):
            grupo  = agrupado[chave]
            if len(grupo) == 1:
                dados_limpos.append(grupo[0])
                continue
            unicas = []
            for linha in grupo:
                if not any(abs(float(linha[2]) - float(u[2])) < 1e-6 for u in unicas):
                    unicas.append(linha)
            dados_limpos.extend(unicas)

        return [tabela[0]] + dados_limpos


# =============================================================================
# BLOCO 4 — INTERATIVIDADE DOS DIAGRAMAS
# =============================================================================

def ativar_interatividade_simples(fig: Figure, canvas) -> None:
    """
    Conecta callbacks de mouse ao canvas Matplotlib para interatividade
    nos diagramas de gradiente térmico.

    Funcionalidades
    ---------------
    • Hover  : linha vertical, ponto destacado e tooltip (posição + valor)
    • Scroll : zoom no eixo Y centrado no cursor
    • Duplo clique : restaura limites originais do eixo Y

    Parâmetros
    ----------
    fig    : Figure — figura retornada por plotar_cortante() ou plotar_momento()
    canvas : FigureCanvas — canvas associado à figura
    """
    data = getattr(fig, 'interactive_data', None)
    if data is None:
        return

    ax     = data['ax']
    xs_sec = data['xs_secoes']
    ys_sec = data['ys_secoes']
    ylabel = data['ylabel']
    y_lo_orig, y_hi_orig = ax.get_ylim()

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
        if event.inaxes is not ax or event.xdata is None:
            vline.set_alpha(0.0)
            dot.set_alpha(0.0)
            tooltip.set_visible(False)
            canvas.draw_idle()
            return
        idx   = int(np.argmin(np.abs(xs_sec - event.xdata)))
        x_sec = float(xs_sec[idx])
        y_sec = float(ys_sec[idx])
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
        if event.inaxes is not ax:
            return
        y_lo, y_hi = ax.get_ylim()
        y_c   = float(event.ydata) if event.ydata is not None else (y_lo + y_hi) / 2.0
        fator = 0.85 if event.button == 'up' else (1.0 / 0.85)
        ax.set_ylim(y_c - (y_c - y_lo) * fator, y_c + (y_hi - y_c) * fator)
        canvas.draw_idle()

    def on_click(event):
        if event.inaxes is ax and event.dblclick:
            ax.set_ylim(y_lo_orig, y_hi_orig)
            canvas.draw_idle()

    canvas.mpl_connect('motion_notify_event', on_move)
    canvas.mpl_connect('scroll_event',        on_scroll)
    canvas.mpl_connect('button_press_event',  on_click)
