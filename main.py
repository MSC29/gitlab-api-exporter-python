import asyncio
from datetime import datetime
import os
import re
from typing import Any, Dict
import typing
import requests
from python_graphql_client import GraphqlClient
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS
from config import ConfigurationMapper

from entities import JobCoverageEntity, JobScoreEntity, ProjectDetailEntity
from models_storage import FloatScoreModel


def main():
    config = ConfigurationMapper(os.getenv("ENV", "local")).config

    graphql_client = build_graphql_client(config.gitlab_url, config.gitlab_token)
    influx_client = build_influx_client(config.influx_url, config.influx_token, config.influx_org)

    user_projects_results = get_project_details_query(graphql_client, config.gitlab_username)
    project_details = [create_project_entity(p["project"]) for p in user_projects_results["data"]["user"]["projectMemberships"]["nodes"]]

    for project_detail in project_details:
        project_detail.pylint_job.score = get_code_quality(config.gitlab_token, project_detail.id, project_detail.pylint_job.id)
        project_detail.bandit_job.score = get_security_sast_issues(config.gitlab_token, project_detail.id, project_detail.bandit_job.id)
        project_detail.safety_job.score = get_vulnerable_dependencies(config.gitlab_token, project_detail.id, project_detail.safety_job.id)

        db_models = build_db_models(project_detail)
        write_to_influx(influx_client, config.influx_org, db_models)


def build_authentication_header(token: str) -> Dict[str, str]:
    return {"authorization": f"Bearer {token}"}


def build_graphql_client(url: str, token: str) -> GraphqlClient:
    headers = build_authentication_header(token)
    client = GraphqlClient(endpoint=url, headers=headers)

    return client


def build_influx_client(url: str, token: str, org: str) -> GraphqlClient:
    client = influxdb_client.InfluxDBClient(
        url=url,
        token=token,
        org=org
    )

    return client


def get_job_trace(token: str, project_id: str, job_id: str) -> str:
    headers = build_authentication_header(token)
    trace = requests.get(f"https://gitlab.com/api/v4/projects/{project_id}/jobs/{job_id}/trace", headers=headers)

    return trace.text


def get_project_details_query(client: GraphqlClient, username: str) -> Any:
    query = """
        query GetProjectDetailsQuery($username: String!) {
            user(username: $username) {
                projectMemberships {
                    nodes {
                        project {
                            pipelines(first: 1) {
                                nodes {
                                test_job: job(name: "test") {
                                    coverage
                                    id
                                    name
                                }
                                pylint_job: job(name: "pylint") {
                                    coverage
                                    id
                                    name
                                }
                                bandit_job: job(name: "bandit") {
                                    coverage
                                    id
                                    name
                                }
                                safety_job: job(name: "safety") {
                                    coverage
                                    id
                                    name
                                }
                            }
                        }
                        mergeRequests(state: opened) {
                            count
                        }
                        id
                        name
                        }
                    }
                }
            }
        }
    """
    variables = {"username": username}

    data = asyncio.run(client.execute_async(query=query, variables=variables))

    return data


def create_project_entity(project: Any) -> ProjectDetailEntity:
    pipeline_node = project["pipelines"]["nodes"][0]

    test_job_pipeline = pipeline_node["test_job"]
    test_job = JobCoverageEntity(
        id=extract_api_id_from_gid(test_job_pipeline["id"]),
        coverage=test_job_pipeline["coverage"],
        name=test_job_pipeline["name"]
    )

    pylint_job_pipeline = pipeline_node["pylint_job"]
    pylint_job = JobScoreEntity(
        id=extract_api_id_from_gid(pylint_job_pipeline["id"]),
        score=0.0,
        name=pylint_job_pipeline["name"]
    )

    bandit_job_pipeline = pipeline_node["bandit_job"]
    bandit_job = JobScoreEntity(
        id=extract_api_id_from_gid(bandit_job_pipeline["id"]),
        score=0.0,
        name=bandit_job_pipeline["name"]
    )

    safety_job_pipeline = pipeline_node["safety_job"]
    safety_job = JobScoreEntity(
        id=extract_api_id_from_gid(safety_job_pipeline["id"]),
        score=0.0,
        name=safety_job_pipeline["name"]
    )

    return ProjectDetailEntity(
        id=extract_api_id_from_gid(project["id"]),
        name=project["name"],
        merge_requests=project["mergeRequests"]["count"],
        test_job=test_job,
        bandit_job=bandit_job,
        pylint_job=pylint_job,
        safety_job=safety_job
    )


def extract_api_id_from_gid(gid: str) -> str:
    search_result = re.search(r"gid://gitlab/([a-zA-Z0-9:]+)/(\d+)", gid)
    if search_result:
        return search_result.group(2)
    return ""


def get_code_quality(token: str, project_id: str, job_id: str) -> float:
    trace = get_job_trace(token, project_id, job_id)

    search_result = re.search(r"Your code has been rated at ([-0-9.]*)/10", trace)
    if search_result:
        return float(search_result.group(1))
    return 0


def get_security_sast_issues(token: str, project_id: str, job_id: str) -> int:
    trace = get_job_trace(token, project_id, job_id)

    search_result_undefined = re.search(r"Undefined: (\d)", trace)
    search_result_low = re.search(r"Low: (\d)", trace)
    search_result_medium = re.search(r"Medium: (\d)", trace)
    search_result_high = re.search(r"High: (\d)", trace)

    score_undefined = int(search_result_undefined.group(1)) if search_result_undefined else 0
    score_low = int(search_result_low.group(1)) if search_result_low else 0
    score_medium = int(search_result_medium.group(1)) if search_result_medium else 0
    score_high = int(search_result_high.group(1)) if search_result_high else 0

    return score_undefined + score_low + score_medium + score_high


def get_vulnerable_dependencies(token: str, project_id: str, job_id: str) -> int:
    trace = get_job_trace(token, project_id, job_id)

    search_result = re.search(r"Safety found (\d) vulnerabilities", trace)
    if search_result:
        return int(search_result.group(1))
    return 0


def build_db_models(project: ProjectDetailEntity) -> typing.List[FloatScoreModel]:
    models = []
    time = datetime.now()
    project_id = project.id
    project_name = project.name

    models.append(FloatScoreModel(
        time,
        project_id,
        project_name,
        metric="merge_request",
        score=float(project.merge_requests)
    ))

    models.append(FloatScoreModel(
        time,
        project_id,
        project_name,
        metric="code_quality",
        score=project.pylint_job.score
    ))

    models.append(FloatScoreModel(
        time,
        project_id,
        project_name,
        metric="security_sast",
        score=project.bandit_job.score
    ))

    models.append(FloatScoreModel(
        time,
        project_id,
        project_name,
        metric="vulnerable_dependencies",
        score=project.safety_job.score
    ))

    models.append(FloatScoreModel(
        time,
        project_id,
        project_name,
        metric="test_coverage",
        score=project.test_job.coverage
    ))

    return models


def write_to_influx(client, org: str, models: typing.List[FloatScoreModel]) -> None:
    write_api = client.write_api(write_options=SYNCHRONOUS)

    for model in models:
        p = influxdb_client.Point(model.metric).field("score", model.score).tag("project_id", model.project_id).tag("project_name", model.project_name)
        write_api.write(bucket="test", org=org, record=p)


main()
