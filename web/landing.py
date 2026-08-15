"""Anonymous FastVoice landing page."""
from fasthtml.common import *

from web.brand import APP_NAME, DESCRIPTION, TAGLINE
from web.components import WAVE_MARK, metadata


def landing_page():
    return (
        *metadata(APP_NAME, DESCRIPTION),
        Div(
            Header(
                A(Div(NotStr(WAVE_MARK), cls="brand-mark"), Span(APP_NAME), href="/", cls="public-brand"),
                Nav(A("Product", href="#product"), A("Developers", href="/developers"), A("GitHub", href="https://github.com/predictivelabsai/FastVoice"), aria_label="Public"),
                A("Sign in", href="/login", cls="sign-in-link"),
                cls="public-nav",
            ),
            Main(
                Section(
                    Div(
                        Span("Open voice automation", cls="hero-kicker"),
                        H1(TAGLINE),
                        P(DESCRIPTION, cls="hero-copy"),
                        Div(
                            A("Start building", href="/login", cls="primary-action"),
                            A("Explore the API", href="/developers", cls="secondary-action"),
                            cls="hero-actions",
                        ),
                        Div(
                            Span("Self-hosted"), Span("Bring your own models"), Span("Browser + telephony"),
                            cls="proof-line",
                        ),
                        cls="hero-content",
                    ),
                    Div(
                        Div(
                            Div(Span("Customer support agent"), Span("Draft", cls="badge badge-draft"), cls="canvas-head"),
                            Div(
                                Article(Span("Start", cls="node-kind"), Strong("Welcome caller"), P("Greet naturally and identify the reason for calling."), cls="flow-node node-start"),
                                Div(cls="flow-line line-one"),
                                Article(Span("Agent", cls="node-kind"), Strong("Resolve request"), P("Use knowledge, tools and live context."), cls="flow-node node-agent"),
                                Div(cls="flow-line line-two"),
                                Article(Span("End", cls="node-kind"), Strong("Close the call"), P("Confirm next steps and say goodbye."), cls="flow-node node-end"),
                                cls="mini-canvas",
                            ),
                            cls="product-window",
                        ),
                        cls="hero-visual",
                    ),
                    cls="hero",
                ),
                Section(
                    Div(
                        Span("One open control plane", cls="section-kicker"),
                        H2("From first prompt to production call."),
                        P("Build the conversation, test it with your microphone, connect a number, and inspect every run without handing your data to a black box."),
                        cls="section-intro",
                    ),
                    Div(
                        Article(Span("01"), H3("Design visually"), P("Compose typed conversation nodes, tools, conditions, context extraction and post-call actions.")),
                        Article(Span("02"), H3("Speak before shipping"), P("Run browser calls and text simulations against the exact workflow draft you are editing.")),
                        Article(Span("03"), H3("Deploy on your terms"), P("Use xAI or another provider, your telephony account, and infrastructure you control.")),
                        cls="feature-grid",
                    ),
                    id="product",
                    cls="feature-section",
                ),
                Section(
                    Div(Span("Built for integration", cls="section-kicker"), H2("A voice platform that is also an API."), P("Automate agents, campaigns and run analysis through the Python SDK, REST API and MCP server.")),
                    A("Read developer documentation", href="/developers", cls="primary-action"),
                    cls="developer-band",
                ),
            ),
            Footer(
                Span("FastVoice is part of the open-source FastSME suite."),
                A("View all products", href="https://fastsme.com/products"),
                cls="public-footer",
            ),
            cls="public-page",
        ),
    )
