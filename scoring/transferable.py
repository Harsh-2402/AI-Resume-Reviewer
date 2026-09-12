"""Technology relationship map used for JD ↔ candidate skill matching.

Match levels (spec §22): Direct Match, Strongly Related (same family, e.g. AWS↔Azure),
Transferable (same broader group, e.g. Flask↔Express), Missing.
"""
from utils.text import tokens

ALIASES: dict[str, str] = {
    "reactjs": "react", "react.js": "react", "nodejs": "node.js", "node": "node.js",
    "postgres": "postgresql", "k8s": "kubernetes", "sklearn": "scikit-learn",
    "amazon web services": "aws", "google cloud platform": "gcp", "google cloud": "gcp",
    "microsoft azure": "azure", "js": "javascript", "ts": "typescript", "golang": "go",
    "cpp": "c++", "csharp": "c#", "mongo": "mongodb", "powerbi": "power bi",
    "apache spark": "spark", "pyspark": "spark", "apache airflow": "airflow",
    "express.js": "express", "expressjs": "express", "vuejs": "vue", "vue.js": "vue",
    "angularjs": "angular", "nextjs": "next.js", "chromadb": "chroma",
    "llama index": "llamaindex", "rest api": "rest", "restful": "rest", "restful apis": "rest",
    "rest apis": "rest", "ci/cd": "ci-cd", "cicd": "ci-cd", "github action": "github actions",
    "tensorflow 2": "tensorflow", "tf": "tensorflow", "ms sql": "sql server", "mssql": "sql server",
    "apache kafka": "kafka", "scikit learn": "scikit-learn", "html5": "html", "css3": "css",
    "sql (postgresql)": "postgresql", "gen ai": "generative ai", "genai": "generative ai",
    "llms": "llm", "large language models": "llm", "machine learning": "ml",
    "deep learning": "dl", "natural language processing": "nlp", "computer vision": "cv",
    "amazon s3": "s3", "aws lambda": "lambda", "amazon ec2": "ec2",
}

FAMILIES: dict[str, list[str]] = {
    "cloud": ["aws", "azure", "gcp", "digitalocean", "heroku", "oracle cloud"],
    "frontend_framework": ["react", "angular", "vue", "svelte", "next.js", "nuxt", "remix"],
    "sql_database": ["postgresql", "mysql", "sql server", "sqlite", "mariadb", "oracle", "sql", "cockroachdb"],
    "nosql_database": ["mongodb", "dynamodb", "cassandra", "couchdb", "firestore", "firebase"],
    "cache": ["redis", "memcached"],
    "python_web": ["fastapi", "flask", "django", "django rest framework", "starlette"],
    "js_backend": ["node.js", "express", "nestjs", "koa", "hapi", "fastify"],
    "java_backend": ["spring", "spring boot", "jakarta ee", "micronaut", "quarkus"],
    "dotnet": [".net", "asp.net", "asp.net core", "blazor"],
    "deep_learning": ["pytorch", "tensorflow", "keras", "jax"],
    "ml_libs": ["scikit-learn", "xgboost", "lightgbm", "catboost"],
    "ml_general": ["ml", "dl", "nlp", "cv", "generative ai", "llm"],
    "data_libs": ["pandas", "numpy", "polars"],
    "messaging": ["kafka", "rabbitmq", "activemq", "sqs", "pubsub", "nats"],
    "containers": ["docker", "podman"],
    "orchestration": ["kubernetes", "docker swarm", "ecs", "eks", "gke", "aks", "openshift", "helm"],
    "ci_cd": ["ci-cd", "github actions", "gitlab ci", "jenkins", "circleci", "travis ci", "azure devops", "argo cd"],
    "iac": ["terraform", "pulumi", "cloudformation", "ansible", "bicep"],
    "data_processing": ["spark", "hadoop", "flink", "beam", "dask", "hive"],
    "workflow_orchestration": ["airflow", "prefect", "dagster", "luigi"],
    "data_warehouse": ["snowflake", "bigquery", "redshift", "databricks", "synapse"],
    "etl_tools": ["dbt", "fivetran", "talend", "informatica"],
    "bi": ["tableau", "power bi", "looker", "metabase", "superset", "qlik"],
    "c_family": ["c", "c++", "c#"],
    "jvm_langs": ["java", "kotlin", "scala"],
    "systems_langs": ["rust", "go"],
    "scripting_langs": ["python", "ruby", "perl", "php"],
    "js_langs": ["javascript", "typescript"],
    "mobile": ["android", "ios", "swift", "react native", "flutter", "kotlin multiplatform"],
    "vector_db": ["pinecone", "weaviate", "chroma", "milvus", "faiss", "qdrant", "pgvector"],
    "llm_frameworks": ["langchain", "langgraph", "llamaindex", "haystack", "semantic kernel", "crewai", "autogen"],
    "vcs": ["git", "github", "gitlab", "bitbucket"],
    "testing": ["pytest", "unittest", "jest", "mocha", "junit", "selenium", "cypress", "playwright", "postman"],
    "api": ["rest", "graphql", "grpc", "websockets"],
    "os_shell": ["linux", "unix", "bash", "shell scripting", "powershell"],
    "web_basics": ["html", "css", "tailwind", "bootstrap", "sass"],
    "storage": ["s3", "gcs", "blob storage"],
    "serverless": ["lambda", "cloud functions", "azure functions"],
    "monitoring": ["prometheus", "grafana", "datadog", "elk", "splunk", "cloudwatch"],
    "auth": ["oauth", "oauth2", "jwt", "openid", "saml"],
}

# Families whose members are close substitutes → "Strongly Related".
STRONG_FAMILIES = {
    "cloud", "frontend_framework", "sql_database", "python_web", "deep_learning", "ml_libs",
    "messaging", "ci_cd", "iac", "orchestration", "data_warehouse", "bi", "workflow_orchestration",
    "vector_db", "llm_frameworks", "testing", "api", "data_processing", "etl_tools", "nosql_database",
    "storage", "serverless", "monitoring", "auth", "js_backend", "java_backend", "containers",
}

# Broader groups: same group, different family → "Transferable".
GROUPS: dict[str, set[str]] = {
    "backend": {"python_web", "js_backend", "java_backend", "dotnet"},
    "database": {"sql_database", "nosql_database", "cache", "vector_db"},
    "languages": {"c_family", "jvm_langs", "systems_langs", "scripting_langs", "js_langs"},
    "ml": {"deep_learning", "ml_libs", "ml_general", "llm_frameworks", "data_libs"},
    "data": {"data_processing", "workflow_orchestration", "data_warehouse", "etl_tools", "bi"},
    "devops": {"containers", "orchestration", "ci_cd", "iac", "monitoring", "serverless"},
    "infra": {"cloud", "storage", "serverless"},
}

_FAMILY_OF: dict[str, str] = {tech: fam for fam, techs in FAMILIES.items() for tech in techs}
_GROUP_OF: dict[str, str] = {fam: grp for grp, fams in GROUPS.items() for fam in fams}


def canonical(tech: str) -> str:
    key = (tech or "").strip().lower().strip("•-*·,.;:()[]")
    key = " ".join(key.split())
    return ALIASES.get(key, key)


def family_of(tech: str) -> str | None:
    return _FAMILY_OF.get(canonical(tech))


def group_of(tech: str) -> str | None:
    fam = family_of(tech)
    return _GROUP_OF.get(fam) if fam else None


def _token_match(a: str, b: str) -> bool:
    """'aws' matches 'aws lambda'; 'python' matches 'python 3'; but 'c' must not match 'c++'."""
    ta, tb = set(tokens(a)), set(tokens(b))
    if not ta or not tb:
        return False
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return short.issubset(long_) and all(len(t) > 1 for t in short)


def classify_match(jd_skill: str, candidate_skills: list[str]) -> tuple[str, str]:
    """Return (status, matched_by) for one JD skill against the candidate's skills."""
    target = canonical(jd_skill)
    if not target:
        return "Missing", ""
    canon_map: dict[str, str] = {}
    for skill in candidate_skills:
        c = canonical(skill)
        if c and c not in canon_map:
            canon_map[c] = skill

    if target in canon_map:
        return "Direct Match", canon_map[target]
    for c, original in canon_map.items():
        if _token_match(target, c):
            return "Direct Match", original

    fam = _FAMILY_OF.get(target)
    if fam:
        for c, original in canon_map.items():
            if _FAMILY_OF.get(c) == fam:
                return ("Strongly Related" if fam in STRONG_FAMILIES else "Transferable"), original
        grp = _GROUP_OF.get(fam)
        if grp:
            for c, original in canon_map.items():
                cfam = _FAMILY_OF.get(c)
                if cfam and _GROUP_OF.get(cfam) == grp:
                    return "Transferable", original
    return "Missing", ""


def build_skill_matrix(jd_skills: list[str], candidate_skills: list[str]) -> list[tuple[str, str, str]]:
    return [(skill, *classify_match(skill, candidate_skills)) for skill in jd_skills]


def technologies_in_text(text: str, technologies: list[str]) -> list[str]:
    """Which of `technologies` appear (canonically) in free text such as a README or repo name."""
    corpus = " " + " ".join(tokens(text)) + " "
    found: list[str] = []
    for tech in technologies:
        c = canonical(tech)
        if not c or len(c) < 2:
            continue
        if f" {c} " in corpus or (len(tokens(c)) > 1 and c in corpus):
            found.append(tech)
    return found
