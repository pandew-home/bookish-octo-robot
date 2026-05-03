# Versioned API Docs

Use the generated Kubernetes API reference for the live cluster version instead of assuming a fixed docs version.

## Docs URL Pattern

Derive the docs URL from `/version`:

- major: `1`
- minor: `34`, `34+`, or another value with non-digit suffixes

Normalize the minor version to digits only, then build:

`https://kubernetes.io/docs/reference/generated/kubernetes-api/v{major}.{minor}/`

Examples:

- `/version -> {"major": "1", "minor": "34"}` => `https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.34/`
- `/version -> {"major": "1", "minor": "34+"}` => `https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.34/`
- `/version -> {"major": "1", "minor": "33"}` => `https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.33/`

## Usage Rules

- Query `/version` before relying on generated API docs.
- Use the derived `docs_url` returned by the helper script when explaining fields or choosing raw API paths.
- If the live cluster version and a user's requested docs version differ, call out the mismatch explicitly.
- If `/version` is unavailable, state that the exact docs URL could not be derived and continue with observed API evidence.
- Use `--discover-api` when the correct API group, preferred version, or resource plural is unknown.

## Common Stable Paths

Many common troubleshooting paths stay stable across adjacent versions, including:

- `/version`
- `/api/v1/namespaces`
- `/api/v1/nodes`
- `/api/v1/namespaces/{namespace}/pods`
- `/apis/apps/v1/namespaces/{namespace}/deployments`
- `/apis/events.k8s.io/v1/namespaces/{namespace}/events`
- `/apis/discovery.k8s.io/v1/namespaces/{namespace}/endpointslices`
- `/apis/networking.k8s.io/v1/namespaces/{namespace}/ingresses`
- `/apis/rbac.authorization.k8s.io/v1/clusterroles`

Use the derived docs URL to confirm the exact fields and subresources before asserting version-specific behavior.

## Discovery Mode

The helper script can query:

- `/api` for core versions
- `/api/{version}` for core resources
- `/apis` for grouped APIs
- `/apis/{groupVersion}` for live resource lists in each preferred version

Use that output to confirm whether a CRD, aggregated API, or resource kind exists before building raw API paths.
