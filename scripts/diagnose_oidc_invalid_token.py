#!/usr/bin/env python3
"""Octop SSO `invalid_token` 诊断脚本（YNU IdP 专用版，交互式）。

流程:
    Step A  只读诊断: discovery + JWKS + token endpoint 假 code 探测
    Step B  构造 /authserver/oidc/authorize URL → 用户在浏览器完成登录
            → 把 IdP 回跳地址栏里的查询串（code=...&state=...&nonce=...）
              粘贴回终端
    Step C  用回调参数做完整测试:
              1) token_endpoint 换 id_token（client_secret_post / basic 两种方式都试）
              2) 解析 id_token header/payload（复现 "missing a key ID"）
              3) JWKS 验签（kid 缺失时回退唯一 key）
              4) userinfo_endpoint 用 access_token 拉用户信息
              5) 输出与 Octop 校验逻辑（iss/aud/nonce/alg/kid）的对照结论

用法:
    python scripts/diagnose_oidc_invalid_token.py \
        --issuer http://ids-oidc-discovery.functions.appwrite.itc.ynu.edu.cn \
        --client-id <client-id> \
        --client-secret <client-secret> \
        --redirect-uri https://your-octop-host/api/auth/oidc/callback

只读诊断，不改 Octop 代码/数据库。secret 只用于本次请求，不落盘。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import sys
import urllib.parse

import httpx

WELL_KNOWN = "/.well-known/openid-configuration"
ALLOWED_ALGS = ("RS256", "ES256")


# ---------------------------------------------------------------- utilities


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(seg: str) -> bytes:
    return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))


def jwt_header_payload(token: str) -> tuple[dict, dict]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError(f"not a JWT (got {len(parts)} segments)")
    header = json.loads(b64url_decode(parts[0]))
    payload = json.loads(b64url_decode(parts[1]))
    return header, payload


def section(title: str) -> None:
    print(f"\n{'=' * 62}\n== {title}\n{'=' * 62}")


def parse_callback_params(raw: str) -> dict[str, str]:
    """解析用户粘贴的回调查询串 / 完整 URL 里的参数。"""
    raw = raw.strip()
    if "?" in raw:
        raw = raw.split("?", 1)[1]
    if "#" in raw:
        raw = raw.split("#", 1)[0]
    return {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}


def prompt_callback() -> dict[str, str]:
    print(
        "\n[操作] 在浏览器中打开上面的 authorize URL 并完成登录。\n"
        "[操作] IdP 会 302 到你的 redirect_uri（可能打不开页面，没关系）。\n"
        "[操作] 复制地址栏里的查询参数或完整 URL 粘贴到这里："
    )
    while True:
        try:
            raw = input("callback> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[中止]")
            sys.exit(130)
        if not raw:
            continue
        params = parse_callback_params(raw)
        if "code" in params:
            print(f"[收到] code={params['code'][:12]}... state={params.get('state', '(无)')!r} "
                  f"nonce={params.get('nonce', '(无)')!r}")
            return params
        print("[重试] 参数里没有 code，请粘贴回跳地址栏的完整内容。")


# ---------------------------------------------------------------- main flow


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--issuer", required=True, help="issuer 或完整 discovery URL")
    ap.add_argument("--client-id", required=True)
    ap.add_argument("--client-secret", required=True)
    ap.add_argument("--redirect-uri", required=True)
    ap.add_argument("--no-interactive", action="store_true",
                    help="只跑 Step A，不进入浏览器交互")
    args = ap.parse_args()

    issuer = args.issuer.rstrip("/")
    discovery_url = issuer if issuer.endswith(WELL_KNOWN) else issuer + WELL_KNOWN
    client = httpx.Client(timeout=30.0, follow_redirects=False)

    # ============================================== Step A: 只读诊断
    section("Step A-1. Discovery 文档")
    resp = client.get(discovery_url)
    resp.raise_for_status()
    discovery = resp.json()
    print(json.dumps(discovery, indent=2, ensure_ascii=False))

    doc_issuer = discovery.get("issuer", "")
    print(f"\n[检查] 配置 issuer = {issuer!r}")
    print(f"[检查] 文档   issuer = {doc_issuer!r}")
    if doc_issuer != issuer:
        print("[警告] 两者不一致（Octop 用文档 issuer 校验 iss claim）。")

    jwks_uri = discovery["jwks_uri"]
    token_endpoint = discovery["token_endpoint"]
    authz_endpoint = discovery["authorization_endpoint"]
    userinfo_endpoint = discovery.get("userinfo_endpoint", "")

    section("Step A-2. JWKS")
    jwks_resp = client.get(jwks_uri)
    jwks_resp.raise_for_status()
    jwks = jwks_resp.json()
    keys = jwks.get("keys", [])
    print(f"共 {len(keys)} 把 key:")
    for k in keys:
        print(
            f"  - kid={k.get('kid')!r} kty={k.get('kty')!r} "
            f"alg={k.get('alg')!r} use={k.get('use')!r}"
        )
    single_key = len(keys) == 1
    jwks_has_kidless = any(not k.get("kid") for k in keys)
    if jwks_has_kidless:
        print("[发现] JWKS 里有**没有 kid 的 key** —— 单密钥 IdP 省略 kid。")
    elif single_key:
        print("[发现] JWKS 只有一把 key（带 kid）—— IdP 签发 token 时仍可能省略 kid。")

    section("Step A-3. Token endpoint 行为探测（假 code，只看错误风格）")
    resp = client.post(token_endpoint, data={
        "grant_type": "authorization_code",
        "code": "DIAGNOSTIC_INVALID_CODE",
        "redirect_uri": args.redirect_uri,
        "client_id": args.client_id,
        "client_secret": args.client_secret,
    })
    print(f"[client_secret_post] HTTP {resp.status_code}: {resp.text[:300]}")
    resp = client.post(token_endpoint, data={
        "grant_type": "authorization_code",
        "code": "DIAGNOSTIC_INVALID_CODE",
        "redirect_uri": args.redirect_uri,
    }, auth=(args.client_id, args.client_secret))
    print(f"[client_secret_basic] HTTP {resp.status_code}: {resp.text[:300]}")

    if args.no_interactive:
        print("\n[--no-interactive] 到此结束。")
        return 0

    # ============================================== Step B: authorize + 浏览器登录
    section("Step B. 构造 authorize URL（浏览器登录）")
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    code_verifier = secrets.token_urlsafe(48)
    code_challenge = b64url(hashlib.sha256(code_verifier.encode()).digest())
    query = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": args.client_id,
        "redirect_uri": args.redirect_uri,
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })
    authorize_url = f"{authz_endpoint}?{query}"
    print("请在浏览器打开：\n")
    print(authorize_url)
    print(f"\n[记录] 期望 state  = {state}")
    print(f"[记录] 本次 nonce  = {nonce}")
    print(f"[记录] code_verifier = {code_verifier}")

    cb = prompt_callback()
    code = cb["code"]

    # ============================================== Step C: 完整测试
    section("Step C-1. token_endpoint 换 id_token")

    def try_token(style: str) -> httpx.Response:
        if style == "client_secret_post":
            return client.post(token_endpoint, data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": args.redirect_uri,
                "client_id": args.client_id,
                "client_secret": args.client_secret,
                "code_verifier": code_verifier,
            })
        return client.post(token_endpoint, data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": args.redirect_uri,
            "code_verifier": code_verifier,
        }, auth=(args.client_id, args.client_secret))

    token_resp: httpx.Response | None = None
    used_style = ""
    for style in ("client_secret_post", "client_secret_basic"):
        r = try_token(style)
        print(f"[{style}] HTTP {r.status_code}: {r.text[:400]}")
        if r.status_code == 200:
            token_resp = r
            used_style = style
            break
    if token_resp is None:
        print("\n!! 两种 client 认证方式都失败。检查 code 是否已用过/过期、")
        print("   redirect_uri 是否与 authorize 时一致、PKCE 是否被 IdP 支持。")
        return 1
    print(f"\n[成功] client 认证方式: {used_style}")

    body = token_resp.json()
    id_token = body.get("id_token")
    access_token = body.get("access_token")
    print(f"token 响应字段: {sorted(body.keys())}")
    if not id_token:
        print("!! 响应里没有 id_token（scope 需要含 openid）")
        return 1

    section("Step C-2. id_token 结构分析（复现 Octop 的报错点）")
    header, payload = jwt_header_payload(id_token)
    print("HEADER :", json.dumps(header, ensure_ascii=False))
    print("PAYLOAD:", json.dumps(
        {k: payload.get(k) for k in ("iss", "aud", "sub", "exp", "iat", "nonce", "preferred_username", "name")},
        ensure_ascii=False))
    alg = header.get("alg")
    kid = header.get("kid")
    print(f"\n  alg = {alg!r}   (Octop 只允许 {ALLOWED_ALGS})")
    print(f"  kid = {kid!r}   ← 缺失时 Octop 抛 'ID token is missing a key ID'")

    ok = True
    if alg not in ALLOWED_ALGS:
        print(f"  [不一致] alg={alg!r} 不在 Octop 白名单，即使 kid 修好也会被拒。")
        ok = False
    if payload.get("iss") != doc_issuer:
        print(f"  [不一致] iss={payload.get('iss')!r} != discovery issuer，Octop 会拒。")
        ok = False

    section("Step C-3. JWKS 验签（模拟修复后的 Octop）")
    try:
        import jwt as pyjwt

        target = None
        if kid:
            target = next((k for k in keys if k.get("kid") == kid), None)
            if target is None:
                print(f"!! JWKS 里找不到 kid={kid!r} 的 key")
        elif single_key:
            target = keys[0]
            print("[回退] id_token 缺 kid 且 JWKS 仅一把 key → 直接用该 key 验签")
        if target is not None:
            pub = pyjwt.PyJWK.from_dict(target).key
            claims = pyjwt.decode(
                id_token,
                pub,
                algorithms=list(ALLOWED_ALGS),
                audience=args.client_id,
                issuer=doc_issuer,
                leeway=60,
                options={"require": ["exp", "iat"]},
            )
            print("[验签] 签名 + iss + aud + exp/iat 全部通过 ✓")
            nonce_match = claims.get("nonce") == nonce
            cb_nonce = cb.get("nonce", "")
            print(f"[验签] 本地 nonce  匹配: {nonce_match}")
            if cb_nonce:
                print(f"[验签] 回调参数 nonce 与本地一致: {cb_nonce == nonce}")
            print(f"[验签] sub = {claims.get('sub')!r}")
            print("\n[结论] 修复 kid 回退后，Octop 的全部校验（含 nonce）都能通过。")
        else:
            ok = False
    except Exception as exc:  # noqa: BLE001
        print(f"[验签失败] {type(exc).__name__}: {exc}")
        ok = False

    section("Step C-4. userinfo_endpoint")
    if not userinfo_endpoint:
        print("discovery 未提供 userinfo_endpoint，跳过。")
    elif not access_token:
        print("token 响应没有 access_token，跳过。")
    else:
        r = client.get(userinfo_endpoint, headers={"Authorization": f"Bearer {access_token}"})
        print(f"HTTP {r.status_code}")
        try:
            print(json.dumps(r.json(), indent=2, ensure_ascii=False))
        except ValueError:
            print(r.text[:500])

    section("总结")
    print(f"  client 认证方式        : {used_style}")
    print(f"  id_token 缺 kid        : {kid is None}  ← 'missing a key ID' 根因")
    print(f"  alg 在 Octop 白名单    : {alg in ALLOWED_ALGS}")
    print(f"  iss 与 discovery 一致  : {payload.get('iss') == doc_issuer}")
    print(f"  JWKS 单 key            : {single_key}  → 可回退验签")
    print(f"  修复后可登录           : {'是' if ok else '否（见上文不一致项）'}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
