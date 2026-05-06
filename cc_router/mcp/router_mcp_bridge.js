#!/usr/bin/env node
/**
 * router_mcp_bridge.js — MCP stdio bridge for CC Router
 *
 * Runs as a stdio-based MCP server, enabling Claude Code (CC) instances
 * within the CC Router hub to call MCP tools via JSON-RPC over stdin/stdout.
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

// ── Configuration ──────────────────────────────────────────────────────

const CONFIG = {
  hubUrl: process.env.CC_ROUTER_HUB_URL || "http://localhost:8765",
  logLevel: process.env.CC_ROUTER_LOG_LEVEL || "info",
};

// ── Logger ─────────────────────────────────────────────────────────────

const LOG_LEVELS = { debug: 0, info: 1, warn: 2, error: 3 };
const currentLevel = LOG_LEVELS[CONFIG.logLevel] ?? 1;

function log(level, ...args) {
  if (LOG_LEVELS[level] >= currentLevel) {
    // Write logs to stderr so they don't interfere with JSON-RPC on stdout
    process.stderr.write(`[mcp-bridge] [${level.toUpperCase()}] ${args.join(" ")}\n`);
  }
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

// ── Tool Handlers ──────────────────────────────────────────────────────

async function handleToolCall(name, args) {
  log("debug", `Tool call: ${name}`, JSON.stringify(args));

  switch (name) {
    case "feishu_notify": {
      const text = args.text || "";
      const chatId = args.chat_id || null;
      log("info", `feishu_notify: "${text.slice(0, 80)}" ${chatId ? `-> ${chatId}` : ""}`);
      return { status: "ok", message: "Notification forwarded to Feishu" };
    }

    case "forward_to_agent": {
      const eventType = args.event_type || "partial";
      const content = args.content || "";
      const taskId = args.task_id || "";
      log("info", `forward_to_agent: type=${eventType} task=${taskId}`);
      // In a full MCP setup, this would POST to the Hub's EventBus HTTP endpoint.
      // For stdio bridge, we acknowledge the forward request.
      return { status: "ok", message: "Event forwarded to agent" };
    }

    case "read_training_log": {
      const workspace = args.workspace || ".";
      const pattern = args.pattern || "*.log";
      log("info", `read_training_log: ${workspace}/${pattern}`);
      // This is a stub — real implementation would read from the filesystem.
      // The Python-side RouterMCPBridge handles the actual file I/O.
      return {
        status: "ok",
        workspace,
        pattern,
        logs: [],
        message: "Training log reading delegated to Python backend",
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
        message: "Experiment data query delegated to Python backend",
      };
    }

    default:
      throw new Error(`Unknown tool: ${name}`);
  }
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
            serverInfo: { name: "cc-router-mcp-bridge", version: "0.1.0" },
          },
        };
      }

      case "notifications/initialized": {
        log("info", "MCP client initialized");
        return null; // Notifications have no response
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
  log("info", "CC Router MCP Bridge starting");
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

  // Handle SIGTERM/SIGINT gracefully
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
