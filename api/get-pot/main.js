"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const session_manager_1 = require("./session_manager");
const version_1 = require("./version");
const commander_1 = require("commander");
const express_1 = __importDefault(require("express"));
const body_parser_1 = __importDefault(require("body-parser"));
const program = new commander_1.Command().option("-p, --port <PORT>").parse();
const options = program.opts();
const PORT_NUMBER = options.port || 4416;
const httpServer = (0, express_1.default)();
httpServer.use(body_parser_1.default.json());
httpServer.listen({
    host: "0.0.0.0",
    port: PORT_NUMBER,
});
console.log(`Started POT server (v${version_1.VERSION}) on port ${PORT_NUMBER}`);
const sessionManager = new session_manager_1.SessionManager();
httpServer.post("/get_pot", async (request, response) => {
    if (request.body.data_sync_id) {
        console.error("data_sync_id is deprecated, use content_binding instead");
        process.exit(1);
    }
    if (request.body.visitor_data) {
        console.error("visitor_data is deprecated, use content_binding instead");
        process.exit(1);
    }
    const contentBinding = request.body.content_binding;
    const proxy = request.body.proxy;
    const bypassCache = request.body.bypass_cache || false;
    const sourceAddress = request.body.source_address;
    const disableTlsVerification = request.body.disable_tls_verification || false;
    try {
        const sessionData = await sessionManager.generatePoToken(contentBinding, proxy, bypassCache, sourceAddress, disableTlsVerification);
        response.send(sessionData);
    }
    catch (e) {
        console.error(`Failed while generating POT. err.name = ${e.name}. err.message = ${e.message}. err.stack = ${e.stack}`);
        response.status(500).send({ error: JSON.stringify(e) });
    }
});
httpServer.post("/invalidate_caches", async (request, response) => {
    sessionManager.invalidateCaches();
    response.send();
});
httpServer.get("/ping", async (request, response) => {
    response.send({
        token_ttl_hours: process.env.TOKEN_TTL || 6,
        server_uptime: process.uptime(),
        version: version_1.VERSION,
    });
});
//# sourceMappingURL=main.js.map