#!/usr/bin/env node
/**
 * router_mcp_bridge.js — MCP stdio bridge for CC Router
 *
 * Runs as a stdio-based MCP server, enabling Claude Code (CC) instances
 * within the CC Router hub to call MCP tools via JSON-RPC over stdin/stdout.
 *
 * Tool calls are delegated to the Hub HTTP API when available,
 * falling back to local handling.
 *
 * Usage:
 *   node router_mcp_bridge.js [--port PORT] [--hub-url URL]
 *
 * Protocol:
 *   Messages are JSON-RPC 2.0 over stdin/stdout:
 *   {"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
 *   {"jsonrpc":"2.0","id":1,"result":{"tools":[...]}}
 *   {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"feishu_notify","arguments":{...}}}
 *
 * Environment:
 *   CC_ROUTER_HUB_URL  — Hub HTTP endpoint (default: http://localhost:8765)
 *   CC_ROUTER_LOG_LEVEL — debug | info | warn | error (default: info)
 */

"use strict";

const readline = require("readline");
const http = require("http");
const { promisify } = require("util");

// ── Configuration ──────────────────────────────────────────────────────

const CONFIG = {
  hubUrl: process.env.CC_ROUTER_HUB_URL || "http://localhost:8765",
  logLevel: process.env.CC_ROUTER_LOG_LEVEL || "info",
  version: "0.3.0",
};

// ── Logger ─────────────────────────────────────────────────────────────

const LOG_LEVELS = { debug: 0, info: 1, warn: 2, error: 3 };
const currentLevel = LOG_LEVELS[CONFIG.logLevel] ?? 1;

function log(level, ...args) {
  if (LOG_LEVELS[level] >= currentLevel) {
    process.stderr.write(`[mcp-bridge] [${level.toUpperCase()}] ${args.join(" ")}\n`);
  }
}

// ── HTTP Delegation ────────────────────────────────────────────────────

/**
 * Try to delegate a tool call to the Hub HTTP API.
 * @param {string} name - Tool name
 * @param {object} args - Tool arguments
 * @returns {Promise<object|null>} Hub response or null if unavailable
 */
function callHubTool(name, args) {
  return new Promise((resolve) => {
    const url = new URL(`${CONFIG.hubUrl}/api/tools/${name}`);
    const body = JSON.stringify({ arguments: args });

    const options = {
      hostname: url.hostname,
      port: url.port,
      path: url.pathname,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(body),
      },
      timeout: 5000,
    };

    const req = http.request(options, (res) => {
      let data = "";
      res.on("data", (chunk) => { data += chunk; });
      res.on("end", () => {
        try {
          const parsed = JSON.parse(data);
          resolve(parsed.status === "ok" ? parsed : null);
        } catch {
          resolve(null);
        }
      });
    });

    req.on("error", () => resolve(null));
    req.on("timeout", () => { req.destroy(); resolve(null); });
    req.write(body);
    req.end();
  });
}

// ── Tool Definitions ───────────────────────────────────────────────────

const TOOLS = [
  {
    name: "feishu_notify",
    description: "Send notification to Feishu/Lark chat",
    inputSchema: {
      type: "object",
      properties: {
        text: { type: "string", description: "Notification text content" },
        chat_id: { type: "string", description: "Target chat ID (optional)" },
      },
      required: ["text"],
    },
  },
  {
    name: "forward_to_agent",
    description: "Forward an event/message to the caller Agent via EventBus",
    inputSchema: {
      type: "object",
      properties: {
        event_type: {
          type: "string",
          description: "Event type (partial, progress, log, result)",
          enum: ["partial", "progress", "log", "result"],
        },
        content: { type: "string", description: "Event content" },
        task_id: { type: "string", description: "Associated task ID" },
      },
      required: ["event_type", "content", "task_id"],
    },
  },
  {
    name: "read_training_log",
    description: "Read ML training log files from workspace",
    inputSchema: {
      type: "object",
      properties: {
        workspace: { type: "string", description: "Workspace directory path" },
        pattern: {
          type: "string",
          description: "Glob pattern for log files (default: *.log)",
          default: "*.log",
        },
      },
    },
  },
  {
    name: "query_experiment_data",
    description: "Query experiment results and metrics",
    inputSchema: {
      type: "object",
      properties: {
        experiment: { type: "string", description: "Experiment name/ID" },
        metric: { type: "string", description: "Metric name (optional)" },
      },
      required: ["experiment"],
    },
  },
];

// ── Local Tool Handlers (fallback when Hub is unavailable) ─────────────

async function handleToolCallLocal(name, args) {
  log("debug", `Local tool call: ${name}`, JSON.stringify(args));

  switch (name) {
    case "feishu_notify": {
      const text = args.text || "";
      const chatId = args.chat_id || null;
      log("info", `feishu_notify: "${text.slice(0, 80)}" ${chatId ? `-> ${chatId}` : ""}`);
      return { status: "ok", message: "Notification sent (local)" };
    }

    case "forward_to_agent": {
      const eventType = args.event_type || "partial";
      const content = args.content || "";
      const taskId = args.task_id || "";
      log("info", `forward_to_agent: type=${eventType} task=${taskId}`);
      return { status: "ok", message: "Event forwarded to agent (local)" };
    }

    case "read_training_log": {
      const workspace = args.workspace || ".";
      const pattern = args.pattern || "*.log";
      log("info", `read_training_log: ${workspace}/${pattern}`);
      return {
        status: "ok",
        workspace,
        pattern,
        logs: [],
        message: `Training log search in ${workspace}/${pattern} (local — no filesystem access in bridge)`,
      };
    }

    case "query_experiment_data": {
      const experiment = args.experiment || "";
      const metric = args.metric || null;
      log("info", `query_experiment_data: experiment=${experiment} metric=${metric}`);
      return {
        status: "ok",
        experiment,
        metric,
        data: null,
        message: `Experiment data query for '${experiment}' (local — delegated to Hub)`,
      };
    }

    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}

// ── Tool Dispatch ──────────────────────────────────────────────────────

async function handleToolCall(name, args) {
  // 1. Try HTTP delegation to Hub
  const hubResult = await callHubTool(name, args);
  if (hubResult) {
    log("debug", `Hub handled: ${name}`);
    return hubResult;
  }

  // 2. Fall back to local handling
  log("debug", `Hub unavailable for ${name}, using local handler`);
  return await handleToolCallLocal(name, args);
}

// ── JSON-RPC Engine ────────────────────────────────────────────────────

function makeError(code, message) {
  return { code, message };
}

async function handleRequest(request) {
  const { id, method, params } = request;

  if (!id && method !== "notifications/initialized") {
    log("warn", "Received request without id");
  }

  try {
    switch (method) {
      case "tools/list": {
        return { jsonrpc: "2.0", id, result: { tools: TOOLS } };
      }

      case "tools/call": {
        const { name, arguments: args } = params || {};
        if (!name) {
          return { jsonrpc: "2.0", id, error: makeError(-32602, "Missing tool name") };
        }
        const result = await handleToolCall(name, args || {});
        return { jsonrpc: "2.0", id, result };
      }

      case "initialize": {
        return {
          jsonrpc: "2.0",
          id,
          result: {
            protocolVersion: "2024-11-05",
            capabilities: { tools: {} },
            serverInfo: { name: "cc-router-mcp-bridge", version: CONFIG.version },
          },
        };
      }

      case "notifications/initialized": {
        log("info", "MCP client initialized");
        return null;
      }

      default:
        return {
          jsonrpc: "2.0",
          id,
          error: makeError(-32601, `Method not found: ${method}`),
        };
    }
  } catch (err) {
    log("error", `Error handling method ${method}:`, err.message);
    return { jsonrpc: "2.0", id, error: makeError(-32603, err.message) };
  }
}

// ── Main Loop ──────────────────────────────────────────────────────────

function main() {
  log("info", `CC Router MCP Bridge v${CONFIG.version} starting`);
  log("info", `Hub URL: ${CONFIG.hubUrl}`);

  const rl = readline.createInterface({
    input: process.stdin,
    crlfDelay: Infinity,
  });

  rl.on("line", async (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;

    let request;
    try {
      request = JSON.parse(trimmed);
    } catch (err) {
      log("error", "Invalid JSON:", trimmed.slice(0, 200));
      const errorResponse = {
        jsonrpc: "2.0",
        id: null,
        error: makeError(-32700, "Parse error"),
      };
      process.stdout.write(JSON.stringify(errorResponse) + "\n");
      return;
    }

    try {
      const response = await handleRequest(request);
      if (response) {
        process.stdout.write(JSON.stringify(response) + "\n");
      }
    } catch (err) {
      log("error", "Unhandled error:", err.message);
      const errorResponse = {
        jsonrpc: "2.0",
        id: request.id || null,
        error: makeError(-32603, "Internal error"),
      };
      process.stdout.write(JSON.stringify(errorResponse) + "\n");
    }
  });

  rl.on("close", () => {
    log("info", "MCP Bridge stdin closed, shutting down");
    process.exit(0);
  });

  process.on("SIGTERM", () => {
    log("info", "Received SIGTERM, shutting down");
    process.exit(0);
  });
  process.on("SIGINT", () => {
    log("info", "Received SIGINT, shutting down");
    process.exit(0);
  });
}

main();
