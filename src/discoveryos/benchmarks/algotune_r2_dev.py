from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from discoveryos.benchmarks.algotune_dev import UPSTREAM_REVISION
from discoveryos.benchmarks.task_types import normalized_source
from discoveryos.util import digest_bytes, digest_json


ADAPTER_ID = "discoveryos.algotune_r2_contract_dev.v1"
EVALUATOR_REGIME = "DISCOVERYOS_STDLIB_ALGOTUNE_R2_CONTRACT_DEV_V1"
UPSTREAM_BINDINGS = {
    "multi_dim_knapsack": ("f3b91d57f5aa97f0007517ec27a7b52682ead505385c62bf76207db4c0b4fa0f", "5322dd2dafb9e707eb0d832c1be6325ad8e32dba373f792f2b34d60032dfde69"),
    "job_shop_scheduling": ("fccbaff7f4eaa1bd86b9193d09d08feb983f8b117a5a207e931264c68f0a03d7", "406d208bf6995178cd8831997a33eeb9ea483f07054c7a6132cfe39e6ad6afdc"),
    "capacitated_facility_location": ("c9583142dc6d05b83478c9f4f1523ea27531785860fdd609d22b9cc9f48d4b36", "7b1573d78853ebb0555fe6f88e9f6b13601a1c1d515aae188d05203b6c9943de"),
    "graph_coloring": ("04d1487b5b09df5a49ba8898edb5723fce473ca379cf169e59fbadb6dcd90610", "dc141b2c3f84f3087a2f312db7a732df866fa24ddacb10e20f888197022ee6fa"),
    "max_flow_min_cost": ("9c01d07b5fc744d8be9eab0a01a86770b7acd6d7ca4639cd9dfe374ed45c7ed1", "f1e9af21f2dc451d5e9cfdde494347ac5397ab85e9bf928d2c8c12cf0722ce84"),
    "earth_movers_distance": ("7a8eb8370c2a6ce6d759feb3373d82da9f072fb2cada0bcc80e2b00180b25a34", "da451300093ebbe0a478f4e2e5ca728a574c4915a93e7419a44e0ea1f0ed0c21"),
    "kcenters": ("e5d85b8729f8110a7acf508002e1a7a25fbcd59dd5cb432c751071c004fa6f12", "73790849fed03a9554c7d0b63107017104512d538126fdfb0c1243d9e2d28062"),
    "max_clique": ("8045bc3d86e1e255d9eac90cb66a6eac2396277cdc81c3ca38f99be18aff3c32", "4872bd5efc94d7cd32fa8811a250e1d423781a75b2d35f32299c58f07b02695c"),
    "max_independent_set": ("067777db79a5bfcc7848ea83565541ba8410b799d801c50dc5e3f18991573fec", "f490fb7e3b558250b4c63e2f89a011870898e9e35dda8571b6d4e6b078f9b817"),
    "minimum_dominating_set": ("33be629506f3847799eebe9256c7c3228153a19ad05113e2ec7f6bb1a1cf904d", "350b82067949846a584413265820126e88b0881fa620c9174b712b26c6b13556"),
}


@dataclass(frozen=True, slots=True)
class R2Spec:
    family_id: str
    upstream_task: str
    instance_id: str
    seed: int
    scale: int
    initial_source: str
    public_tests_source: str
    evaluator_body: str


def _source(value: str) -> str:
    return normalized_source(textwrap.dedent(value).strip() + "\n")


KNAPSACK = _source(
    """
    def solve(problem):
        values, demands, supplies = problem
        states = {tuple(0 for _ in supplies): (0, ())}
        for item, value in enumerate(values):
            updated = dict(states)
            for used, (score, chosen) in states.items():
                nxt = tuple(used[r] + demands[item][r] for r in range(len(supplies)))
                if all(nxt[r] <= supplies[r] for r in range(len(supplies))):
                    previous = updated.get(nxt)
                    candidate = (score + value, chosen + (item,))
                    if previous is None or candidate[0] > previous[0]:
                        updated[nxt] = candidate
            states = updated
        return list(max(states.values(), key=lambda entry: entry[0])[1])
    """
)
KNAPSACK_PUBLIC = _source(
    """
    from algorithm import solve
    problem = ([8, 5, 6], [[3, 2], [2, 3], [4, 1]], [6, 5])
    result = solve(problem)
    assert len(result) == len(set(result))
    assert sum(problem[0][i] for i in result) == 13
    """
)
KNAPSACK_EVAL = _source(
    """
    def make_cases(seed, scale):
        rng = random.Random(seed)
        cases = []
        for offset in range(2):
            n = scale + offset
            values = [rng.randrange(3, 25) for _ in range(n)]
            demands = [[rng.randrange(1, 8), rng.randrange(1, 8)] for _ in range(n)]
            supplies = [sum(row[r] for row in demands) // 3 for r in range(2)]
            cases.append((values, demands, supplies))
        return cases
    def reference(problem):
        values, demands, supplies = problem
        best = 0
        for mask in range(1 << len(values)):
            used = [0] * len(supplies)
            value = 0
            for item in range(len(values)):
                if mask & (1 << item):
                    value += values[item]
                    for resource in range(len(supplies)):
                        used[resource] += demands[item][resource]
            if all(used[r] <= supplies[r] for r in range(len(supplies))):
                best = max(best, value)
        return best
    def valid_solution(problem, actual, optimum):
        values, demands, supplies = problem
        if not isinstance(actual, list) or len(actual) != len(set(actual)):
            return False
        if not all(isinstance(item, int) and 0 <= item < len(values) for item in actual):
            return False
        if any(sum(demands[item][r] for item in actual) > supplies[r] for r in range(len(supplies))):
            return False
        return sum(values[item] for item in actual) == optimum
    """
)


JOB_SHOP = _source(
    """
    def solve(problem):
        jobs = problem["jobs"]
        machine_count = problem["num_machines"]
        best_makespan = sum(duration for job in jobs for _, duration in job) + 1
        best_starts = None
        def visit(next_ops, job_ready, machine_ready, starts, remaining):
            nonlocal best_makespan, best_starts
            if remaining == 0:
                makespan = max(job_ready, default=0)
                if makespan < best_makespan:
                    best_makespan, best_starts = makespan, [list(row) for row in starts]
                return
            if max(job_ready, default=0) >= best_makespan:
                return
            for job_index, operation_index in enumerate(next_ops):
                if operation_index >= len(jobs[job_index]):
                    continue
                machine, duration = jobs[job_index][operation_index]
                start = max(job_ready[job_index], machine_ready[machine])
                next_next = list(next_ops); next_next[job_index] += 1
                next_job = list(job_ready); next_job[job_index] = start + duration
                next_machine = list(machine_ready); next_machine[machine] = start + duration
                next_starts = [list(row) for row in starts]; next_starts[job_index].append(start)
                visit(next_next, next_job, next_machine, next_starts, remaining - 1)
        visit([0] * len(jobs), [0] * len(jobs), [0] * machine_count, [[] for _ in jobs], sum(map(len, jobs)))
        return best_starts or []
    """
)
JOB_SHOP_PUBLIC = _source(
    """
    from algorithm import solve
    problem = {"num_machines": 2, "jobs": [[(0, 2), (1, 1)], [(1, 2), (0, 1)]]}
    result = solve(problem)
    assert len(result) == 2 and all(len(row) == 2 for row in result)
    assert max(result[j][-1] + problem["jobs"][j][-1][1] for j in range(2)) == 3
    """
)
JOB_SHOP_EVAL = _source(
    """
    def make_cases(seed, scale):
        rng = random.Random(seed)
        cases = []
        for offset in range(2):
            jobs = []
            for _ in range(scale + offset):
                machines = list(range(3)); rng.shuffle(machines)
                jobs.append([(machine, rng.randrange(1, 6)) for machine in machines])
            cases.append({"num_machines": 3, "jobs": jobs})
        return cases
    def schedule_makespan(problem, starts):
        jobs = problem["jobs"]
        if not isinstance(starts, list) or len(starts) != len(jobs): return None
        by_machine = [[] for _ in range(problem["num_machines"])]
        makespan = 0
        for j, job in enumerate(jobs):
            if not isinstance(starts[j], list) or len(starts[j]) != len(job): return None
            for op, (machine, duration) in enumerate(job):
                start = starts[j][op]
                if not isinstance(start, int) or start < 0: return None
                if op and start < starts[j][op - 1] + job[op - 1][1]: return None
                by_machine[machine].append((start, start + duration))
                makespan = max(makespan, start + duration)
        for intervals in by_machine:
            intervals.sort()
            if any(intervals[i][1] > intervals[i + 1][0] for i in range(len(intervals) - 1)): return None
        return makespan
    def reference(problem):
        jobs = problem["jobs"]
        best = [sum(duration for job in jobs for _, duration in job) + 1]
        def visit(next_ops, job_ready, machine_ready, remaining):
            if remaining == 0:
                best[0] = min(best[0], max(job_ready, default=0)); return
            if max(job_ready, default=0) >= best[0]: return
            for j, op in enumerate(next_ops):
                if op >= len(jobs[j]): continue
                machine, duration = jobs[j][op]
                start = max(job_ready[j], machine_ready[machine])
                a=list(next_ops); a[j]+=1
                b=list(job_ready); b[j]=start+duration
                c=list(machine_ready); c[machine]=start+duration
                visit(a,b,c,remaining-1)
        visit([0]*len(jobs), [0]*len(jobs), [0]*problem["num_machines"], sum(map(len,jobs)))
        return best[0]
    def valid_solution(problem, actual, optimum):
        return schedule_makespan(problem, actual) == optimum
    """
)


FACILITY = _source(
    """
    def solve(problem):
        fixed, capacities, demands, costs = (problem[key] for key in ("fixed_costs", "capacities", "demands", "transportation_costs"))
        best = [float("inf"), None]
        loads = [0.0] * len(fixed)
        assignment = [-1] * len(demands)
        def visit(customer, open_set, running):
            if running >= best[0]: return
            if customer == len(demands):
                best[:] = [running, list(assignment)]; return
            for facility in range(len(fixed)):
                if loads[facility] + demands[customer] > capacities[facility]: continue
                extra = costs[facility][customer] + (0.0 if facility in open_set else fixed[facility])
                loads[facility] += demands[customer]; assignment[customer] = facility
                visit(customer + 1, open_set | {facility}, running + extra)
                loads[facility] -= demands[customer]
        visit(0, set(), 0.0)
        chosen = best[1] or []
        status = [facility in set(chosen) for facility in range(len(fixed))]
        matrix = [[1.0 if customer < len(chosen) and chosen[customer] == facility else 0.0 for customer in range(len(demands))] for facility in range(len(fixed))]
        return {"objective_value": best[0], "facility_status": status, "assignments": matrix}
    """
)
FACILITY_PUBLIC = _source(
    """
    from algorithm import solve
    problem={"fixed_costs":[4.0,5.0],"capacities":[4.0,4.0],"demands":[2.0,2.0],"transportation_costs":[[1.0,3.0],[3.0,1.0]]}
    result=solve(problem)
    assert abs(result["objective_value"]-8.0)<1e-9
    assert sum(sum(row) for row in result["assignments"])==2.0
    """
)
FACILITY_EVAL = _source(
    """
    def make_cases(seed, scale):
        rng=random.Random(seed); cases=[]
        for offset in range(2):
            facilities=4; customers=scale+offset
            demands=[rng.randrange(1,4) for _ in range(customers)]
            capacities=[sum(demands)//2+3 for _ in range(facilities)]
            cases.append({"fixed_costs":[float(rng.randrange(5,15)) for _ in range(facilities)],"capacities":capacities,"demands":demands,"transportation_costs":[[float(rng.randrange(1,15)) for _ in range(customers)] for _ in range(facilities)]})
        return cases
    def objective(problem, actual):
        required=("objective_value","facility_status","assignments")
        if not isinstance(actual,dict) or any(key not in actual for key in required): return None
        status=actual["facility_status"]; matrix=actual["assignments"]
        f=len(problem["fixed_costs"]); c=len(problem["demands"])
        if len(status)!=f or len(matrix)!=f or any(len(row)!=c for row in matrix): return None
        chosen=[]
        for customer in range(c):
            assigned=[facility for facility in range(f) if matrix[facility][customer] in (1,1.0,True)]
            if len(assigned)!=1: return None
            chosen.append(assigned[0])
        for facility in range(f):
            load=sum(problem["demands"][customer] for customer in range(c) if chosen[customer]==facility)
            if load>problem["capacities"][facility] or (load>0 and not status[facility]): return None
        return sum(problem["fixed_costs"][facility] for facility in range(f) if status[facility])+sum(problem["transportation_costs"][chosen[customer]][customer] for customer in range(c))
    def reference(problem):
        best=float("inf"); f=len(problem["fixed_costs"]); c=len(problem["demands"])
        for assignment in itertools.product(range(f),repeat=c):
            if any(sum(problem["demands"][j] for j in range(c) if assignment[j]==i)>problem["capacities"][i] for i in range(f)): continue
            opened=set(assignment)
            value=sum(problem["fixed_costs"][i] for i in opened)+sum(problem["transportation_costs"][assignment[j]][j] for j in range(c))
            best=min(best,value)
        return best
    def valid_solution(problem,actual,optimum):
        value=objective(problem,actual)
        return value is not None and abs(value-optimum)<=1e-8
    """
)


COLORING = _source(
    """
    def solve(problem):
        n=len(problem); order=sorted(range(n),key=lambda node:sum(problem[node]),reverse=True)
        for limit in range(1,n+1):
            colors=[0]*n
            def visit(position):
                if position==n:return True
                node=order[position]
                forbidden={colors[other] for other in range(n) if problem[node][other] and colors[other]}
                for color in range(1,limit+1):
                    if color not in forbidden:
                        colors[node]=color
                        if visit(position+1):return True
                        colors[node]=0
                return False
            if visit(0):return colors
        return []
    """
)
COLORING_PUBLIC = _source(
    """
    from algorithm import solve
    graph=[[0,1,0,1],[1,0,1,0],[0,1,0,1],[1,0,1,0]]
    result=solve(graph)
    assert len(result)==4 and len(set(result))==2
    """
)
COLORING_EVAL = _source(
    """
    def make_cases(seed,scale):
        rng=random.Random(seed); cases=[]
        for offset in range(2):
            n=scale+offset; graph=[[0]*n for _ in range(n)]
            for i in range(n):
                for j in range(i+1,n):
                    if rng.random()<0.42: graph[i][j]=graph[j][i]=1
            cases.append(graph)
        return cases
    def reference(graph):
        n=len(graph); order=sorted(range(n),key=lambda node:sum(graph[node]),reverse=True)
        for limit in range(1,n+1):
            colors=[0]*n
            def visit(pos):
                if pos==n:return True
                node=order[pos]; forbidden={colors[j] for j in range(n) if graph[node][j] and colors[j]}
                for color in range(1,limit+1):
                    if color not in forbidden:
                        colors[node]=color
                        if visit(pos+1):return True
                        colors[node]=0
                return False
            if visit(0):return limit
    def valid_solution(graph,actual,optimum):
        return isinstance(actual,list) and len(actual)==len(graph) and all(isinstance(c,int) and c>0 for c in actual) and all(not graph[i][j] or actual[i]!=actual[j] for i in range(len(graph)) for j in range(i+1,len(graph))) and len(set(actual))==optimum
    """
)


MINCOST_FLOW = _source(
    """
    def solve(problem):
        capacity=[list(row) for row in problem["capacity"]]; costs=problem["cost"]; n=len(capacity); s=problem["s"]; t=problem["t"]
        residual=[list(row) for row in capacity]; residual_cost=[[0]*n for _ in range(n)]; flow=[[0]*n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if capacity[i][j]>0: residual_cost[i][j]=costs[i][j]; residual_cost[j][i]=-costs[i][j]
        while True:
            distance=[float("inf")]*n; parent=[-1]*n; distance[s]=0
            for _ in range(n-1):
                changed=False
                for i in range(n):
                    if distance[i]==float("inf"):continue
                    for j in range(n):
                        if residual[i][j]>0 and distance[i]+residual_cost[i][j]<distance[j]:
                            distance[j]=distance[i]+residual_cost[i][j]; parent[j]=i; changed=True
                if not changed:break
            if parent[t]<0:break
            amount=float("inf"); node=t
            while node!=s: amount=min(amount,residual[parent[node]][node]); node=parent[node]
            node=t
            while node!=s:
                previous=parent[node]; residual[previous][node]-=amount; residual[node][previous]+=amount
                if capacity[previous][node]>0: flow[previous][node]+=amount
                else: flow[node][previous]-=amount
                node=previous
        return flow
    """
)
MINCOST_FLOW_PUBLIC = _source(
    """
    from algorithm import solve
    problem={"capacity":[[0,2,1,0],[0,0,0,2],[0,0,0,1],[0,0,0,0]],"cost":[[0,1,3,0],[0,0,0,1],[0,0,0,1],[0,0,0,0]],"s":0,"t":3}
    result=solve(problem)
    assert sum(result[0])==3 and sum(row[3] for row in result)==3
    """
)
MINCOST_FLOW_EVAL = _source(
    """
    def make_cases(seed,scale):
        rng=random.Random(seed); cases=[]
        for offset in range(2):
            n=scale+offset; capacity=[[0]*n for _ in range(n)]; cost=[[0]*n for _ in range(n)]
            for i in range(n-1): capacity[i][i+1]=rng.randrange(2,8); cost[i][i+1]=rng.randrange(1,8)
            for i in range(n):
                for j in range(i+2,n):
                    if rng.random()<0.35: capacity[i][j]=rng.randrange(1,6); cost[i][j]=rng.randrange(1,10)
            cases.append({"capacity":capacity,"cost":cost,"s":0,"t":n-1})
        return cases
    def flow_stats(problem,flow):
        n=len(problem["capacity"]); s=problem["s"]; t=problem["t"]
        if not isinstance(flow,list) or len(flow)!=n or any(not isinstance(row,list) or len(row)!=n for row in flow):return None
        for i in range(n):
            for j in range(n):
                if not isinstance(flow[i][j],(int,float)) or flow[i][j]<0 or flow[i][j]>problem["capacity"][i][j]:return None
        for node in range(n):
            if node in (s,t):continue
            if abs(sum(flow[i][node] for i in range(n))-sum(flow[node][j] for j in range(n)))>1e-9:return None
        value=sum(flow[s]); incoming=sum(flow[i][t] for i in range(n))
        if abs(value-incoming)>1e-9:return None
        return value,sum(flow[i][j]*problem["cost"][i][j] for i in range(n) for j in range(n))
    def reference(problem):
        capacity=[list(row) for row in problem["capacity"]]; costs=problem["cost"]; n=len(capacity); s=problem["s"]; t=problem["t"]
        residual=[list(row) for row in capacity]; rcost=[[0]*n for _ in range(n)]; flow=[[0]*n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if capacity[i][j]>0:rcost[i][j]=costs[i][j];rcost[j][i]=-costs[i][j]
        while True:
            dist=[float("inf")]*n; parent=[-1]*n;dist[s]=0
            for _ in range(n-1):
                changed=False
                for i in range(n):
                    for j in range(n):
                        if dist[i]!=float("inf") and residual[i][j]>0 and dist[i]+rcost[i][j]<dist[j]:dist[j]=dist[i]+rcost[i][j];parent[j]=i;changed=True
                if not changed:break
            if parent[t]<0:break
            amount=float("inf");node=t
            while node!=s:amount=min(amount,residual[parent[node]][node]);node=parent[node]
            node=t
            while node!=s:
                previous=parent[node];residual[previous][node]-=amount;residual[node][previous]+=amount
                if capacity[previous][node]>0:flow[previous][node]+=amount
                else:flow[node][previous]-=amount
                node=previous
        return flow_stats(problem,flow)
    def valid_solution(problem,actual,optimum):return flow_stats(problem,actual)==optimum
    """
)


EMD = _source(
    """
    def solve(problem):
        costs=problem["cost_matrix"]; n=len(costs); states={0:(0.0,())}
        for source in range(n):
            updated={}
            for mask,(value,path) in states.items():
                for target in range(n):
                    if mask&(1<<target):continue
                    candidate=(value+costs[source][target],path+(target,));key=mask|(1<<target)
                    if key not in updated or candidate[0]<updated[key][0]:updated[key]=candidate
            states=updated
        assignment=states[(1<<n)-1][1];mass=1.0/n
        return {"transport_plan":[[mass if assignment[i]==j else 0.0 for j in range(n)] for i in range(n)]}
    """
)
EMD_PUBLIC = _source(
    """
    from algorithm import solve
    result=solve({"source_weights":[0.5,0.5],"target_weights":[0.5,0.5],"cost_matrix":[[1.0,4.0],[3.0,1.0]]})["transport_plan"]
    assert result==[[0.5,0.0],[0.0,0.5]]
    """
)
EMD_EVAL = _source(
    """
    def make_cases(seed,scale):
        rng=random.Random(seed);cases=[]
        for offset in range(2):
            n=scale+offset; source=[(rng.random(),rng.random()) for _ in range(n)];target=[(rng.random(),rng.random()) for _ in range(n)]
            matrix=[[math.dist(source[i],target[j]) for j in range(n)] for i in range(n)]
            cases.append({"source_weights":[1.0/n]*n,"target_weights":[1.0/n]*n,"cost_matrix":matrix})
        return cases
    def reference(problem):
        costs=problem["cost_matrix"];n=len(costs);states={0:0.0}
        for i in range(n):
            updated={}
            for mask,value in states.items():
                for j in range(n):
                    if mask&(1<<j):continue
                    key=mask|(1<<j);updated[key]=min(updated.get(key,float("inf")),value+costs[i][j])
            states=updated
        return states[(1<<n)-1]/n
    def valid_solution(problem,actual,optimum):
        if not isinstance(actual,dict) or not isinstance(actual.get("transport_plan"),list):return False
        plan=actual["transport_plan"];n=len(problem["source_weights"])
        if len(plan)!=n or any(not isinstance(row,list) or len(row)!=n for row in plan):return False
        if any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for row in plan for v in row):return False
        if any(abs(sum(plan[i])-problem["source_weights"][i])>1e-8 for i in range(n)):return False
        if any(abs(sum(plan[i][j] for i in range(n))-problem["target_weights"][j])>1e-8 for j in range(n)):return False
        value=sum(plan[i][j]*problem["cost_matrix"][i][j] for i in range(n) for j in range(n))
        return abs(value-optimum)<=1e-8
    """
)


KCENTERS = _source(
    """
    import itertools
    def solve(problem):
        graph,k=problem; nodes=sorted(graph);n=len(nodes);dist=[[float("inf")]*n for _ in range(n)]
        for i,node in enumerate(nodes):
            dist[i][i]=0.0
            for neighbor,weight in graph[node].items():dist[i][nodes.index(neighbor)]=float(weight)
        for middle in range(n):
            for i in range(n):
                for j in range(n):dist[i][j]=min(dist[i][j],dist[i][middle]+dist[middle][j])
        best=None
        for centers in itertools.combinations(range(n),min(k,n)):
            value=max(min(dist[node][center] for center in centers) for node in range(n))
            if best is None or value<best[0]:best=(value,centers)
        return [nodes[index] for index in best[1]] if best else []
    """
)
KCENTERS_PUBLIC = _source(
    """
    from algorithm import solve
    graph={"A":{"B":1,"D":1},"B":{"A":1,"C":1},"C":{"B":1,"D":1},"D":{"A":1,"C":1}}
    result=solve((graph,2))
    assert len(result)==2 and set(result)<=set(graph)
    """
)
KCENTERS_EVAL = _source(
    """
    def make_cases(seed,scale):
        rng=random.Random(seed);cases=[]
        for offset in range(2):
            n=scale+offset;nodes=[f"N{i}" for i in range(n)];graph={node:{} for node in nodes}
            for i in range(n):
                for j in range(i+1,n):
                    if j==i+1 or rng.random()<0.3:
                        weight=rng.randrange(1,10);graph[nodes[i]][nodes[j]]=weight;graph[nodes[j]][nodes[i]]=weight
            cases.append((graph,3))
        return cases
    def distances(graph):
        nodes=sorted(graph);n=len(nodes);dist=[[float("inf")]*n for _ in range(n)]
        for i,node in enumerate(nodes):
            dist[i][i]=0
            for neighbor,weight in graph[node].items():dist[i][nodes.index(neighbor)]=weight
        for k in range(n):
            for i in range(n):
                for j in range(n):dist[i][j]=min(dist[i][j],dist[i][k]+dist[k][j])
        return nodes,dist
    def reference(problem):
        graph,k=problem;nodes,dist=distances(graph)
        return min(max(min(dist[node][center] for center in centers) for node in range(len(nodes))) for centers in itertools.combinations(range(len(nodes)),k))
    def valid_solution(problem,actual,optimum):
        graph,k=problem
        if not isinstance(actual,(list,set,tuple)) or len(set(actual))>k or not set(actual)<=set(graph) or not actual:return False
        nodes,dist=distances(graph);indices=[nodes.index(node) for node in set(actual)]
        value=max(min(dist[node][center] for center in indices) for node in range(len(nodes)))
        return abs(value-optimum)<=1e-9
    """
)


def _subset_solver(mode: str) -> str:
    if mode == "clique":
        condition = "all(problem[i][j] for i, j in itertools.combinations(chosen, 2))"
        sizes = "range(n, 0, -1)"
    elif mode == "independent":
        condition = "all(not problem[i][j] for i, j in itertools.combinations(chosen, 2))"
        sizes = "range(n, 0, -1)"
    else:
        condition = "all(node in chosen or any(problem[node][other] for other in chosen) for node in range(n))"
        sizes = "range(1, n + 1)"
    return _source(
        f"""
        import itertools
        def solve(problem):
            n=len(problem)
            for size in {sizes}:
                for chosen in itertools.combinations(range(n),size):
                    if {condition}:return list(chosen)
            return []
        """
    )


SUBSET_PUBLIC = {
    "max_clique": _source("""
        from algorithm import solve
        graph=[[0,1,0,1],[1,0,1,0],[0,1,0,1],[1,0,1,0]]
        result=solve(graph); assert len(result)==2 and all(graph[i][j] for p,i in enumerate(result) for j in result[p+1:])
    """),
    "max_independent_set": _source("""
        from algorithm import solve
        graph=[[0,1,0,1],[1,0,1,0],[0,1,0,1],[1,0,1,0]]
        result=solve(graph); assert len(result)==2 and all(not graph[i][j] for p,i in enumerate(result) for j in result[p+1:])
    """),
    "minimum_dominating_set": _source("""
        from algorithm import solve
        graph=[[0,1,0,1],[1,0,1,0],[0,1,0,1],[1,0,1,0]]
        result=solve(graph); assert len(result)==2
    """),
}


def _subset_eval(mode: str) -> str:
    if mode == "max_clique":
        valid = "all(graph[i][j] for i,j in itertools.combinations(actual,2))"
        objective = "len(actual)==optimum"
        reference_condition = "all(graph[i][j] for i,j in itertools.combinations(chosen,2))"
        sizes = "range(n,0,-1)"
    elif mode == "max_independent_set":
        valid = "all(not graph[i][j] for i,j in itertools.combinations(actual,2))"
        objective = "len(actual)==optimum"
        reference_condition = "all(not graph[i][j] for i,j in itertools.combinations(chosen,2))"
        sizes = "range(n,0,-1)"
    else:
        valid = "all(node in actual or any(graph[node][other] for other in actual) for node in range(len(graph)))"
        objective = "len(actual)==optimum"
        reference_condition = "all(node in chosen or any(graph[node][other] for other in chosen) for node in range(n))"
        sizes = "range(1,n+1)"
    return _source(
        f"""
        def make_cases(seed,scale):
            rng=random.Random(seed);cases=[]
            for offset in range(2):
                n=scale+offset;graph=[[0]*n for _ in range(n)]
                for i in range(n):
                    for j in range(i+1,n):
                        if rng.random()<0.42:graph[i][j]=graph[j][i]=1
                cases.append(graph)
            return cases
        def reference(graph):
            n=len(graph)
            for size in {sizes}:
                for chosen in itertools.combinations(range(n),size):
                    if {reference_condition}:return size
            return 0
        def valid_solution(graph,actual,optimum):
            return isinstance(actual,list) and len(actual)==len(set(actual)) and all(isinstance(node,int) and 0<=node<len(graph) for node in actual) and {valid} and {objective}
        """
    )


_FAMILIES = {
    "multi_dim_knapsack": ("multi_dim_knapsack", KNAPSACK, KNAPSACK_PUBLIC, KNAPSACK_EVAL, 13),
    "job_shop_scheduling": ("job_shop_scheduling", JOB_SHOP, JOB_SHOP_PUBLIC, JOB_SHOP_EVAL, 2),
    "capacitated_facility_location": ("capacitated_facility_location", FACILITY, FACILITY_PUBLIC, FACILITY_EVAL, 6),
    "graph_coloring": ("graph_coloring_assign", COLORING, COLORING_PUBLIC, COLORING_EVAL, 9),
    "max_flow_min_cost": ("max_flow_min_cost", MINCOST_FLOW, MINCOST_FLOW_PUBLIC, MINCOST_FLOW_EVAL, 7),
    "earth_movers_distance": ("earth_movers_distance", EMD, EMD_PUBLIC, EMD_EVAL, 7),
    "kcenters": ("kcenters", KCENTERS, KCENTERS_PUBLIC, KCENTERS_EVAL, 8),
    "max_clique": ("max_clique_cpsat", _subset_solver("clique"), SUBSET_PUBLIC["max_clique"], _subset_eval("max_clique"), 11),
    "max_independent_set": ("max_independent_set_cpsat", _subset_solver("independent"), SUBSET_PUBLIC["max_independent_set"], _subset_eval("max_independent_set"), 11),
    "minimum_dominating_set": ("min_dominating_set", _subset_solver("dominating"), SUBSET_PUBLIC["minimum_dominating_set"], _subset_eval("minimum_dominating_set"), 11),
}


def _evaluator_source(body: str, seed: int, scale: int) -> str:
    header = _source(
        f"""
        import copy
        import itertools
        import json
        import math
        import random
        import statistics
        import time
        from algorithm import solve
        SEED={seed}
        SCALE={scale}
        EVALUATOR_REGIME={EVALUATOR_REGIME!r}
        """
    )
    tail = _source(
        """
        cases=make_cases(SEED,SCALE)
        expected=[reference(copy.deepcopy(problem)) for problem in cases]
        valid=True;error=None
        try:
            for problem,optimum in zip(cases,expected):
                frozen=copy.deepcopy(problem);actual=solve(problem)
                valid=valid and problem==frozen and valid_solution(frozen,actual,optimum)
        except Exception as exc:
            valid=False;error=type(exc).__name__
        timings=[]
        if valid:
            for _ in range(3):
                started=time.perf_counter()
                for problem in cases:solve(copy.deepcopy(problem))
                timings.append(time.perf_counter()-started)
        median_runtime_ms=statistics.median(timings)*1000.0 if timings else None
        score=1.0/(1.0+median_runtime_ms) if valid and median_runtime_ms is not None else 0.0
        print(json.dumps({"metrics":{"score":score,"valid":float(valid),"median_runtime_ms":median_runtime_ms,"case_count":len(cases)},"evaluator_regime":EVALUATOR_REGIME,"error":error},sort_keys=True))
        """
    )
    return header + "\n" + body + "\n" + tail


def r2_specs() -> dict[tuple[str, str], R2Spec]:
    specs = {}
    for family_id, (upstream_task, initial, public, evaluator, scale) in _FAMILIES.items():
        for suffix, seed, offset in (("alpha", 3301, 0), ("beta", 4409, 1)):
            instance_id = f"{family_id}_dev_{suffix}"
            specs[(family_id, instance_id)] = R2Spec(
                family_id, upstream_task, instance_id, seed, scale + offset, initial, public, evaluator
            )
    return specs


def materialize_r2_dev(family: dict[str, Any], instance_id: str, output_dir: Path) -> dict[str, Any]:
    spec = r2_specs().get((family["family_id"], instance_id))
    if spec is None or instance_id not in family.get("instance_ids", []):
        raise ValueError(f"instance is not registered for family: {instance_id}")
    if family.get("upstream_task") != spec.upstream_task:
        raise RuntimeError("registered AlgoTune R2 upstream task binding drift")
    output_dir = output_dir.resolve(); output_dir.mkdir(parents=True, exist_ok=False)
    initial=output_dir/"algorithm.py"; public=output_dir/"public_tests.py"; evaluator=output_dir/"evaluate.py"; contract=output_dir/"task-contract.json"
    initial.write_text(spec.initial_source,encoding="utf-8")
    public.write_text(spec.public_tests_source,encoding="utf-8")
    evaluator.write_text(_evaluator_source(spec.evaluator_body,spec.seed,spec.scale),encoding="utf-8")
    binding=family["development_binding"]
    contract_payload={"schema_version":1,"family_id":spec.family_id,"instance_id":spec.instance_id,"source_id":"algotune","source_revision":UPSTREAM_REVISION,"upstream_task":spec.upstream_task,"upstream_task_sha256":binding["upstream_task_sha256"],"upstream_description_sha256":binding["upstream_description_sha256"],"adapter_id":ADAPTER_ID,"evaluator_regime":EVALUATOR_REGIME,"upstream_evaluator_reused":False,"dependency_profile":"PYTHON_3_11_STANDARD_LIBRARY_ONLY","partition_role":"DEV","seed":spec.seed,"scale":spec.scale,"claim_ceiling":"EXTERNAL_R2_CONTRACT_DERIVED_DEVELOPMENT_ONLY"}
    contract.write_text(json.dumps(contract_payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    payload={**contract_payload,"initial_program_sha256":digest_bytes(initial.read_bytes()),"public_tests_sha256":digest_bytes(public.read_bytes()),"evaluator_sha256":digest_bytes(evaluator.read_bytes()),"task_contract_sha256":digest_bytes(contract.read_bytes())}
    (output_dir/"bank-instance.json").write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return {"family_id":spec.family_id,"instance_id":spec.instance_id,"initial_program_path":str(initial),"public_tests_path":str(public),"evaluator_path":str(evaluator),"evaluator_digest":payload["evaluator_sha256"],"instance_digest":digest_json(payload),"claim_ceiling":contract_payload["claim_ceiling"],"adapter_id":ADAPTER_ID,"source_revision":UPSTREAM_REVISION,"evaluator_regime":EVALUATOR_REGIME,"task_contract_path":str(contract)}
