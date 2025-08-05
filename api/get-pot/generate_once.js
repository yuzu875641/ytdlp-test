"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
const session_manager_1 = require("./session_manager");
const version_1 = require("./version");
const extra_typings_1 = require("@commander-js/extra-typings");
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
// Follow XDG Base Directory Specification: https://specifications.freedesktop.org/basedir-spec/latest/
let cachedir;
if ("XDG_CACHE_HOME" in process.env) {
    cachedir = path.resolve(process.env.XDG_CACHE_HOME || "", "bgutil-ytdlp-pot-provider");
}
else if ("HOME" in process.env) {
    cachedir = path.resolve(process.env.HOME || "", ".cache", "bgutil-ytdlp-pot-provider");
}
else {
    // fall back to a known path if environment variables are not found
    cachedir = path.resolve(__dirname, "..");
}
if (!fs.existsSync(cachedir)) {
    fs.mkdir(cachedir, { recursive: true }, (err) => {
        if (err)
            throw err;
    });
}
const CACHE_PATH = path.resolve(cachedir, "cache.json");
const program = new extra_typings_1.Command()
    .option("-c, --content-binding <content-binding>")
    .option("-v, --visitor-data <visitordata>") // to be removed in a future version
    .option("-d, --data-sync-id <data-sync-id>") // to be removed in a future version
    .option("-p, --proxy <proxy-all>")
    .option("-b, --bypass-cache")
    .option("-s, --source-address <source-address>")
    .option("--disable-tls-verification")
    .option("--version")
    .option("--verbose")
    .exitOverride();
try {
    program.parse();
}
catch (err) {
    if (err.code === "commander.unknownOption") {
        console.log();
        program.outputHelp();
    }
}
const options = program.opts();
(async () => {
    if (options.version) {
        console.log(version_1.VERSION);
        process.exit(0);
    }
    if (options.dataSyncId) {
        console.error("Data sync id is deprecated, use --content-binding instead");
        process.exit(1);
    }
    if (options.visitorData) {
        console.error("Visitor data is deprecated, use --content-binding instead");
        process.exit(1);
    }
    const contentBinding = options.contentBinding;
    const proxy = options.proxy || "";
    const verbose = options.verbose || false;
    const cache = {};
    if (fs.existsSync(CACHE_PATH)) {
        try {
            const parsedCaches = JSON.parse(fs.readFileSync(CACHE_PATH, "utf8"));
            for (const contentBinding in parsedCaches) {
                const parsedCache = parsedCaches[contentBinding];
                if (parsedCache) {
                    const expiresAt = new Date(parsedCache.expiresAt);
                    if (!isNaN(expiresAt.getTime()))
                        cache[contentBinding] = {
                            poToken: parsedCache.poToken,
                            expiresAt,
                            contentBinding: contentBinding,
                        };
                    else
                        console.warn(`Ignored cache entry: invalid expiresAt for content binding '${contentBinding}'.`);
                }
            }
        }
        catch (e) {
            console.warn(`Error parsing cache. e = ${e}`);
        }
    }
    const sessionManager = new session_manager_1.SessionManager(verbose, cache);
    try {
        const sessionData = await sessionManager.generatePoToken(contentBinding, proxy, options.bypassCache || false, options.sourceAddress, options.disableTlsVerification || false);
        try {
            fs.writeFileSync(CACHE_PATH, JSON.stringify(sessionManager.getYoutubeSessionDataCaches(true)), "utf8");
        }
        catch (e) {
            console.warn(`Error writing cache. err.name = ${e.name}. err.message = ${e.message}. err.stack = ${e.stack}`);
        }
        finally {
            console.log(JSON.stringify(sessionData));
        }
    }
    catch (e) {
        console.error(`Failed while generating POT. err.name = ${e.name}. err.message = ${e.message}. err.stack = ${e.stack}`);
        console.log(JSON.stringify({}));
        process.exit(1);
    }
})();
//# sourceMappingURL=generate_once.js.map