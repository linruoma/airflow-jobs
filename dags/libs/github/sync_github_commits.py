import copy
import datetime
import itertools
import requests
import time

from opensearchpy import OpenSearch

from .init_commits import get_github_commits, bulk_github_commits
from ..base_dict.opensearch_index import OPENSEARCH_INDEX_GITHUB_COMMITS, OPENSEARCH_INDEX_CHECK_SYNC_DATA
from ..util.base import do_get_result, github_headers, do_opensearch_bulk, sync_github_commits_check_update_info
from ..util.log import logger


class SyncGithubCommitException(Exception):
    def __init__(self, message, status):
        super().__init__(message, status)
        self.message = message
        self.status = status


def sync_github_commits(github_tokens,
                        opensearch_conn_info,
                        owner, repo):
    github_tokens_iter = itertools.cycle(github_tokens)

    opensearch_client = OpenSearch(
        hosts=[{'host': opensearch_conn_info["HOST"], 'port': opensearch_conn_info["PORT"]}],
        http_compress=True,
        http_auth=(opensearch_conn_info["USER"], opensearch_conn_info["PASSWD"]),
        use_ssl=True,
        verify_certs=False,
        ssl_assert_hostname=False,
        ssl_show_warn=False
    )

    # 取得上次更新github commit 的时间节点

    has_commit_check = opensearch_client.search(index=OPENSEARCH_INDEX_CHECK_SYNC_DATA,
                                                body={
                                                    "size": 1,
                                                    "track_total_hits": True,
                                                    "query": {
                                                        "bool": {
                                                            "must": [
                                                                {
                                                                    "term": {
                                                                        "search_key.type.keyword": {
                                                                            "value": "github_commits"
                                                                        }
                                                                    }
                                                                },
                                                                {
                                                                    "term": {
                                                                        "search_key.owner.keyword": {
                                                                            "value": owner
                                                                        }
                                                                    }
                                                                },
                                                                {
                                                                    "term": {
                                                                        "search_key.repo.keyword": {
                                                                            "value": repo
                                                                        }
                                                                    }
                                                                }
                                                            ]
                                                        }
                                                    },
                                                    "sort": [
                                                        {
                                                            "search_key.update_timestamp": {
                                                                "order": "desc"
                                                            }
                                                        }
                                                    ]
                                                }
                                                )
    if len(has_commit_check["hits"]["hits"]) == 0:
        raise SyncGithubCommitException("没有得到上次github commits 同步的时间")
    github_commits_check = has_commit_check["hits"]["hits"][0]["_source"]["github"]["commits"]

    # 生成本次同步的时间范围：同步到今天的 00:00:00
    since = datetime.datetime.fromtimestamp(github_commits_check["sync_until_timestamp"]).strftime('%Y-%m-%dT00:00:00Z')
    until = datetime.datetime.now().strftime('%Y-%m-%dT00:00:00Z')
    logger.info(f'sync github commits since：{since}，sync until：{until}')

    session = requests.Session()
    for page in range(1, 9999):
        req = get_github_commits(session, github_tokens_iter, owner, repo, page, since, until)
        now_github_commits = req.json()

        if (now_github_commits is not None) and len(now_github_commits) == 0:
            logger.info(f'get github commits end to break:: {owner}/{repo} page_index:{page}')
            break

        bulk_github_commits(now_github_commits, opensearch_client, owner, repo)

        logger.info(f"success get github commits :: {owner}/{repo} page_index:{page}")

        time.sleep(1)

    sync_github_commits_check_update_info(opensearch_client, owner, repo, since, until)

    return "END::sync_github_commits"
