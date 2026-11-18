"""Shared pure-Python numerics: logistic IRLS, linear solve, helpers."""
import math, csv

def solve(A, b):
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(M[r][i]))
        M[i], M[p] = M[p], M[i]
        for r in range(n):
            if r != i and M[r][i] != 0:
                f = M[r][i] / M[i][i]
                M[r] = [a - f * c for a, c in zip(M[r], M[i])]
    return [M[i][n] / M[i][i] for i in range(n)]

def sigmoid(z):
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)

def logistic_irls(X, y, iters=25, ridge=1e-6):
    """Newton-Raphson / IRLS logistic regression. X rows include intercept. y in [0,1]."""
    k = len(X[0])
    beta = [0.0] * k
    for _ in range(iters):
        H = [[0.0] * k for _ in range(k)]
        g = [0.0] * k
        for x, t in zip(X, y):
            p = sigmoid(sum(b * v for b, v in zip(beta, x)))
            w = max(p * (1 - p), 1e-9)
            for i in range(k):
                g[i] += (t - p) * x[i]
                wi = w * x[i]
                Hi = H[i]
                for j in range(i, k):
                    Hi[j] += wi * x[j]
        for i in range(k):
            H[i][i] += ridge
            for j in range(i):
                H[i][j] = H[j][i]
        step = solve(H, g)
        beta = [b + s for b, s in zip(beta, step)]
        if max(abs(s) for s in step) < 1e-8:
            break
    return beta

def logloss_brier(X, y, beta):
    ll = br = 0.0
    for x, t in zip(X, y):
        p = min(max(sigmoid(sum(b * v for b, v in zip(beta, x))), 1e-12), 1 - 1e-12)
        ll -= t * math.log(p) + (1 - t) * math.log(1 - p)
        br += (p - t) ** 2
    return ll / len(y), br / len(y)

def read_csv(path):
    return list(csv.DictReader(open(path, encoding='utf-8')))

def write_csv(path, rows, fields=None):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
