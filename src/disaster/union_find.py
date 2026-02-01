from __future__ import annotations


class UnionFind:
    """
    并查集（Union-Find），用于快速计算连通分量大小。

    设计目标：
    - 只依赖 Python 内置类型
    - 支持大量 union 操作
    - 维护当前最大连通分量大小（max_size）
    """

    def __init__(self, n: int):
        if n < 0:
            raise ValueError(f"n 必须非负：{n}")
        self.parent = list(range(n))
        self.size = [1] * n
        self.max_size = 1 if n > 0 else 0

    def find(self, x: int) -> int:
        parent = self.parent
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return
        size = self.size
        parent = self.parent
        if size[ra] < size[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        size[ra] += size[rb]
        if size[ra] > self.max_size:
            self.max_size = size[ra]

