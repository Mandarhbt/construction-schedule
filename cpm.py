def calculate_cpm(df):
    # Prefer a `Predecessors` list if present, otherwise fall back to singular `Predecessor` values
    use_list = "Predecessors" in df.columns

    # prepare structures
    df["ES"] = 0
    df["EF"] = 0
    df["LF"] = 0
    df["LS"] = 0

    # Build ID -> index map for quick lookup
    id_to_idx = {str(v): k for k, v in df["ID"].items()}

    # Build adjacency and indegree for topological sort
    from collections import defaultdict, deque
    adj = defaultdict(list)
    indeg = {idx: 0 for idx in df.index}

    for idx, row in df.iterrows():
        if use_list:
            preds = row.get("Predecessors") or []
        else:
            preds = [row.get("Predecessor")] if row.get("Predecessor") not in (None, "") else []

        for p in preds:
            pid = str(p)
            if pid not in id_to_idx:
                raise ValueError(f"Predecessor '{pid}' not found for activity ID {row['ID']}")
            pidx = id_to_idx[pid]
            adj[pidx].append(idx)
            indeg[idx] += 1

    # Kahn's algorithm for topological order
    q = deque([n for n, d in indeg.items() if d == 0])
    topo = []
    while q:
        n = q.popleft()
        topo.append(n)
        for s in adj.get(n, []):
            indeg[s] -= 1
            if indeg[s] == 0:
                q.append(s)

    if len(topo) != len(df):
        # Find nodes involved in the cycle and report a readable cycle path
        remaining = set(df.index) - set(topo)

        # DFS to find a cycle and reconstruct path
        visited = set()
        stack = set()
        parent = {}
        cycle = []

        def dfs(u):
            nonlocal cycle
            visited.add(u)
            stack.add(u)
            for v in adj.get(u, []):
                if v not in visited:
                    parent[v] = u
                    if dfs(v):
                        return True
                elif v in stack:
                    # found back edge v <- ... <- u, reconstruct path v->...->u->v
                    path = [v]
                    cur = u
                    while cur != v and cur in parent:
                        path.append(cur)
                        cur = parent[cur]
                    path.append(v)
                    path.reverse()
                    cycle = path
                    return True
            stack.remove(u)
            return False

        start = next(iter(remaining))
        dfs(start)

        if cycle:
            # map indices to IDs for readability
            cycle_ids = [str(df.at[idx, "ID"]) for idx in cycle]
            # write debug CSVs to workspace so user can inspect
            try:
                import os
                debug_dir = os.getcwd()
                df_debug = df[["ID", "Predecessor"]].copy()
                df_debug.to_csv(os.path.join(debug_dir, "cycle_activities_debug.csv"), index=False)
                # edges
                with open(os.path.join(debug_dir, "cycle_edges_debug.csv"), "w", encoding="utf-8") as fh:
                    fh.write("from,to\n")
                    for u, vs in adj.items():
                        u_id = str(df.at[u, "ID"]) if u in df.index else str(u)
                        for v in vs:
                            v_id = str(df.at[v, "ID"]) if v in df.index else str(v)
                            fh.write(f"{u_id},{v_id}\n")
                extra = f" (debug files: cycle_activities_debug.csv, cycle_edges_debug.csv in {debug_dir})"
            except Exception:
                extra = ""
            raise ValueError(f"Cycle detected in activity predecessors; cycle: {' -> '.join(cycle_ids)}" + extra)
        else:
            raise ValueError("Cycle detected in activity predecessors; cannot compute CPM")

    # Forward pass in topological order
    for idx in topo:
        row = df.loc[idx]
        if use_list:
            predecessors = row.get("Predecessors") or []
        else:
            predecessors = [row.get("Predecessor")] if row.get("Predecessor") not in (None, "") else []

        if not predecessors:
            es = 0
        else:
            pred_efs = []
            for pred in predecessors:
                pred_idx = id_to_idx[str(pred)]
                pred_efs.append(df.at[pred_idx, "EF"])
            es = max(pred_efs)

        ef = es + int(row["Duration"])
        df.at[idx, "ES"] = es
        df.at[idx, "EF"] = ef

    project_finish = int(df["EF"].max())

    # Backward pass in reverse topological order
    for idx in reversed(topo):
        row = df.loc[idx]
        succs = adj.get(idx, [])
        if succs:
            lf = min([df.at[s, "LS"] for s in succs])
        else:
            lf = project_finish

        ls = lf - int(row["Duration"])
        df.at[idx, "LF"] = lf
        df.at[idx, "LS"] = ls

    # store float as whole numbers (no decimals)
    df["Float"] = (df["LS"] - df["ES"]).round().astype(int)
    df["Critical"] = (df["Float"] == 0)

    return df