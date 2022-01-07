import itertools
from loguru import logger
from opensearchpy.helpers import scan as os_scan
from oss_know.libs.base_dict.opensearch_index import OPENSEARCH_INDEX_GITHUB_COMMITS, \
    OPENSEARCH_INDEX_GITHUB_ISSUES_TIMELINE
from oss_know.libs.util.opensearch_api import OpensearchAPI
from opensearchpy import OpenSearch


def load_github_ids_by_repo(opensearch_conn_infos, owner, repo):
    """Get GitHub users' ids from GitHub assigned owner and repo."""
    opensearch_client = get_opensearch_client(opensearch_conn_infos)
    init_profile_ids = load_ids_by_github_issues_timeline(opensearch_client, owner,
                                                          repo)
    init_profile_ids += load_ids_by_github_commits(opensearch_client, owner, repo)
    return init_profile_ids


def load_ids_by_github_commits(opensearch_client, owner, repo):
    """Get GitHub users' ids from GitHub commits."""
    logger.debug(f'calling load_ids_by_github_commits for {owner}/{repo}')
    res = get_github_data_by_repo_owner_index_from_os(opensearch_client, owner, repo,
                                                      index=OPENSEARCH_INDEX_GITHUB_COMMITS)
    if not res:
        logger.info(f"There's no github commits in {repo}")
        return []
    # delete duplicated data of GitHub author and GitHub committer
    all_commits_users = set()

    for commit in res:
        raw_data = commit["_source"]["raw_data"]
        if (raw_data["author"] is not None) and ("author" in raw_data) and ("id" in raw_data["author"]):
            all_commits_users.add(raw_data["author"]["id"])
        if (raw_data["committer"] is not None) and ("committer" in raw_data) and ("id" in raw_data["committer"]):
            all_commits_users.add(raw_data["committer"]["id"])

    return list(all_commits_users)


def load_ids_by_github_issues_timeline(opensearch_client, owner, repo):
    """Get GitHub users' ids from GitHub issues timeline ."""

    logger.debug(f'calling load_ids_by_github_issues_timeline for {owner}/{repo}')

    res = get_github_data_by_repo_owner_index_from_os(opensearch_client, owner, repo,
                                                      index=OPENSEARCH_INDEX_GITHUB_ISSUES_TIMELINE)

    if not res:
        logger.info(f"There's no github issues' timeline in {repo}")
        return []

    all_issues_timeline_users = set()
    for issue_timeline in res:
        issue_timeline_raw_data = issue_timeline["_source"]["raw_data"]
        if issue_timeline_raw_data["event"] == "cross-referenced":
            all_issues_timeline_users.add(issue_timeline_raw_data["actor"]["id"])
            all_issues_timeline_users.add(issue_timeline_raw_data["source"]["issue"]["user"]["id"])
        elif issue_timeline_raw_data["event"] != "committed":
            for key in ["user", "actor", "assignee"]:
                if key in issue_timeline_raw_data:
                    all_issues_timeline_users.add(issue_timeline_raw_data[key]["id"])

    return list(all_issues_timeline_users)


def get_github_data_by_repo_owner_index_from_os(opensearch_client, owner, repo, index):
    """Get GitHub users by repo and owner and index from opensearch."""

    # 查询owner+repo所有github issues记录用来提取github issue的user
    res = os_scan(client=opensearch_client, index=index,
                  query={
                      "track_total_hits": True,
                      "query": {
                          "bool": {"must": [
                              {"term": {
                                  "search_key.owner.keyword": {
                                      "value": owner
                                  }
                              }},
                              {"term": {
                                  "search_key.repo.keyword": {
                                      "value": repo
                                  }
                              }}
                          ]}
                      }
                  }, doc_type='_doc', timeout='10m')
    logger.info(f'Get GitHub users by {repo} and {owner} and {index} from opensearch.')
    return res


def load_github_profiles(github_tokens, opensearch_conn_infos, github_users_ids):
    """Get GitHub profiles by ids."""
    # get ids set;
    github_users_ids = list(set(github_users_ids))
    # put GitHub user profile into opensearch if it is not in opensearch
    github_tokens_iter = itertools.cycle(github_tokens)
    opensearch_api = OpensearchAPI()
    opensearch_api.put_profile_into_opensearch(github_ids=github_users_ids, github_tokens_iter=github_tokens_iter,
                                               opensearch_client=get_opensearch_client(opensearch_conn_infos))
    logger.info(load_github_profiles.__doc__)


def get_opensearch_client(opensearch_conn_infos):
    """Get opensearch client to connect to opensearch."""
    opensearch_client = OpenSearch(
        hosts=[{'host': opensearch_conn_infos["HOST"], 'port': opensearch_conn_infos["PORT"]}],
        http_compress=True,
        http_auth=(opensearch_conn_infos["USER"], opensearch_conn_infos["PASSWD"]),
        use_ssl=True,
        verify_certs=False,
        ssl_assert_hostname=False,
        ssl_show_warn=False
    )
    return opensearch_client
