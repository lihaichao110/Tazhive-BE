from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.semconv.attributes.service_attributes import SERVICE_NAME


def setup_tracing(service_name: str = "agent-api"):
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    trace.set_tracer_provider(provider)
    return provider
