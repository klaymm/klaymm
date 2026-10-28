#!/usr/bin/env python3
"""Собирает статистику GitHub-профиля и рисует её в двух SVG: светлом и тёмном.

Использование: generate_stats.py <папка для SVG>
Переменные окружения: GITHUB_TOKEN (обязательно), STATS_USER (логин, обязательно).
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from html import escape

API_URL = "https://api.github.com/graphql"

PROFILE_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositoriesContributedTo(
      first: 1
      contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, REPOSITORY]
    ) { totalCount }
    repositories(
      first: 100
      after: $after
      ownerAffiliations: OWNER
      isFork: false
      orderBy: {field: STARGAZERS, direction: DESC}
    ) {
      nodes { stargazerCount }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

THEMES = {
    "github-stats.svg": {"muted": "#57606a", "accent": "#0969da"},
    "github-stats-dark.svg": {"muted": "#8b949e", "accent": "#58a6ff"},
}

ROWS = (
    ("Звёзды", "stars"),
    ("Коммиты", "commits"),
    ("Pull request'ы", "prs"),
    ("Issues", "issues"),
    ("Вклад в репозитории", "contributed_to"),
    ("Подписчики", "followers"),
)


def graphql(query, variables):
    request = urllib.request.Request(
        API_URL,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Content-Type": "application/json",
            "User-Agent": "profile-stats",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(f"GitHub GraphQL вернул ошибки: {payload['errors']}")
    return payload["data"]


def count_commits(login, first_year, last_year):
    # contributionsCollection отдаёт не больше года за раз, поэтому берём по году на алиас
    fields = "\n".join(
        f'y{year}: contributionsCollection(from: "{year}-01-01T00:00:00Z", to: "{year}-12-31T23:59:59Z") '
        "{ totalCommitContributions restrictedContributionsCount }"
        for year in range(first_year, last_year + 1)
    )
    data = graphql("query($login: String!) { user(login: $login) { %s } }" % fields, {"login": login})
    return sum(
        year["totalCommitContributions"] + year["restrictedContributionsCount"]
        for year in data["user"].values()
    )


def collect_stats(login):
    stars = 0
    after = None
    while True:
        user = graphql(PROFILE_QUERY, {"login": login, "after": after})["user"]
        stars += sum(repo["stargazerCount"] for repo in user["repositories"]["nodes"])
        page = user["repositories"]["pageInfo"]
        if not page["hasNextPage"]:
            break
        after = page["endCursor"]

    first_year = int(user["createdAt"][:4])
    last_year = datetime.now(timezone.utc).year
    return {
        "stars": stars,
        "commits": count_commits(login, first_year, last_year),
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "contributed_to": user["repositoriesContributedTo"]["totalCount"],
        "followers": user["followers"]["totalCount"],
    }


def format_number(value):
    return f"{value:,}".replace(",", "\u00a0")


def render(stats, colors):
    width, row_height, padding = 495, 28, 24
    height = padding * 2 + row_height * len(ROWS) - 8
    rows = []
    for index, (label, key) in enumerate(ROWS):
        y = padding + 14 + index * row_height
        rows.append(f'    <text x="{padding}" y="{y}" class="label">{escape(label)}</text>')
        rows.append(
            f'    <text x="{width - padding}" y="{y}" class="value" text-anchor="end">'
            f"{format_number(stats[key])}</text>"
        )
    body = "\n".join(rows)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Статистика GitHub">
  <style>
    text {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 16px; }}
    .label {{ fill: {colors["muted"]}; }}
    .value {{ fill: {colors["accent"]}; font-weight: 600; }}
  </style>
  <g>
{body}
  </g>
</svg>
"""


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    out_dir = sys.argv[1]
    stats = collect_stats(os.environ["STATS_USER"])
    os.makedirs(out_dir, exist_ok=True)
    for filename, colors in THEMES.items():
        with open(os.path.join(out_dir, filename), "w", encoding="utf-8") as svg:
            svg.write(render(stats, colors))
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
