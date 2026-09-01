# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React, TypeScript, and Vite, confirmed for the frontend branch.

## Users

People who want to assemble and work with heterogeneous intelligences: local and hosted models, agents, tools, services, code, and other people. They need a concrete way to understand what each participant can actually do and safely use them together.

## Product Purpose

Maiku is a substrate for intelligence and the tools any intelligence needs. It turns any system that computes into a Participant with a common descriptor, call convention, and event stream, so people can add, inspect, connect, and use different kinds of intelligence in one shared runtime.

## Positioning

Maiku preserves a participant's native affordances instead of flattening every model, tool, person, and pipeline into a chatbot. Its runtime makes capabilities, artifacts, grants, delegation, and human escalation legible in one system.

## Operating Context

A user creates a local workspace, adds participants through adapters, starts shared sessions, invokes native affordances, reads their event streams and artifacts, and intervenes when a task asks for input or approval. Participants may be models, agents, services, tools, Python objects, MCP servers, A2A agents, REST APIs, CLI tools, ML modules, pipelines, or people.

## Capabilities and Constraints

The first GUI is an interactive local-first demo of the Maiku runtime concepts, built on the frontend branch. It must use the real adapter and descriptor vocabulary and expose a clean runtime-client boundary for live Python sessions later. The underlying runtime is local-first, keeps a SQLite registry, treats artifacts as content-addressed references, and uses narrowing grants for bounded delegation. It does not promise automatic composition or complete hostile-code sandboxing.

## Brand Commitments

Product name: maiku. Existing public phrase: "the universal kawaii adapter (0w0/)". Voice should make deep systems feel approachable without obscuring their technical truth.

## Evidence on Hand

The repository README, specification, adapter guide, and two worked examples are the authoritative product evidence. No customer claims, pricing, testimonials, external integrations, or frontend assets are available; the interface must not fabricate them.

## Product Principles

1. Preserve native capability; do not make everything chat.
2. Make the human a first-class participant, not an exception path.
3. Make permissions, side effects, and waiting states visible before harm occurs.
4. Let any legitimate computing system join without hand-authored registry metadata.
5. Keep the shared session and event stream understandable to a first-time visitor.

## Accessibility & Inclusion

Keyboard-operable controls, semantic structure, readable contrast, visible focus states, and motion that respects reduced-motion preferences are required.
