import java.io.*;
import java.lang.management.*;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.*;

/** One application thread, blocking TCP, no dependencies or frameworks. */
public final class Handler {
    static final long MAX_INTEGER = (1L << 53) - 1;
    final Map<String, String> args;
    final int bufferBytes, flushEvery, maxMessageBytes, allocationRounds, retainLimit;
    final String scenario;
    final Path output;
    final ArrayDeque<Map<String, Object>> retained = new ArrayDeque<>();
    final com.sun.management.OperatingSystemMXBean os =
        (com.sun.management.OperatingSystemMXBean) ManagementFactory.getOperatingSystemMXBean();
    final RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
    final List<GarbageCollectorMXBean> collectors = ManagementFactory.getGarbageCollectorMXBeans();
    BufferedOutputStream writer;
    volatile Object blackhole;
    long count, totalCount, evicted, startedNs, cpuStartedNs, startUptimeMs;
    boolean measuring;
    Map<String, Object> gcBefore, finalMetrics;

    Handler(Map<String, String> args) throws IOException {
        this.args = args;
        bufferBytes = positive(args, "buffer-bytes", 65536);
        flushEvery = positive(args, "flush-every", 256);
        maxMessageBytes = positive(args, "max-message-bytes", 1048576);
        allocationRounds = positive(args, "allocation-rounds", 8);
        retainLimit = positive(args, "retain", 1000000);
        scenario = args.getOrDefault("scenario", "A");
        if (!Set.of("A", "B", "C").contains(scenario)) throw new IllegalArgumentException("scenario");
        if (!args.containsKey("output")) throw new IllegalArgumentException("--output is required");
        output = Path.of(args.get("output"));
        writer = openWriter(true);
        gcBefore = gcStats();
    }

    BufferedOutputStream openWriter(boolean append) throws IOException {
        return new BufferedOutputStream(new FileOutputStream(output.toFile(), append), bufferBytes);
    }

    static int positive(Map<String, String> args, String key, int fallback) {
        int value = Integer.parseInt(args.getOrDefault(key, Integer.toString(fallback)));
        if (value < 1) throw new IllegalArgumentException(key + " must be positive");
        return value;
    }

    Map<String, Object> gcStats() {
        Map<String, Object> stats = new LinkedHashMap<>();
        for (GarbageCollectorMXBean bean : collectors) {
            stats.put(bean.getName(), Map.of("collections", bean.getCollectionCount(),
                                           "collection_time_ms", bean.getCollectionTime()));
        }
        return stats;
    }

    Map<String, Object> begin() throws IOException {
        if (measuring) throw new IllegalArgumentException("measurement already started");
        writer.close();
        writer = openWriter(false);
        retained.clear();
        System.gc(); // Discard warm-up cycles outside the measured interval.
        count = evicted = 0;
        gcBefore = gcStats();
        startUptimeMs = runtime.getUptime();
        cpuStartedNs = os.getProcessCpuTime();
        startedNs = System.nanoTime();
        measuring = true;
        return Map.of("control", "begin", "started_ns", startedNs);
    }

    static Map<String, Object> parseMessage(String line) {
        Object value = Json.parse(line);
        if (!(value instanceof Map)) throw new IllegalArgumentException("top-level JSON must be an object");
        @SuppressWarnings("unchecked") Map<String, Object> message = (Map<String, Object>) value;
        return message;
    }

    static Map<String, Object> transform(Map<String, Object> message) {
        if (!(message.get("id") instanceof Long id) || id < 0)
            throw new IllegalArgumentException("id must be a nonnegative integer");
        if (!(message.get("qty") instanceof Long qty)) throw new IllegalArgumentException("qty must be an integer");
        if (!(message.get("price") instanceof Number price)) throw new IllegalArgumentException("price must be a number");
        if (!(message.get("symbol") instanceof String symbol)) throw new IllegalArgumentException("symbol must be an ASCII string");
        for (int i = 0; i < symbol.length(); i++)
            if (symbol.charAt(i) > 127) throw new IllegalArgumentException("symbol must be ASCII");
        double notional = qty.doubleValue() * price.doubleValue();
        if (!Double.isFinite(notional)) throw new IllegalArgumentException("notional overflow");
        message.put("processed_ts", System.currentTimeMillis());
        message.put("notional", notional);
        message.put("symbol", symbol.toUpperCase(Locale.ROOT));
        return message;
    }

    void handle(String line, Map<String, Object> message, OutputStream replies) throws IOException {
        transform(message);
        if (scenario.equals("B")) {
            List<Object> scratch = new ArrayList<>();
            for (int i = 0; i < allocationRounds; i++) {
                Map<String, Object> copy = parseMessage(line);
                scratch.add(List.of(copy, (Json.stringify(copy) + "\n").getBytes(StandardCharsets.UTF_8)));
            }
            blackhole = scratch; // Make temporary allocations observable to the JIT.
            blackhole = null;
        } else if (scenario.equals("C")) {
            Map<String, Object> node = new LinkedHashMap<>();
            Map<String, Object> peer = new LinkedHashMap<>();
            node.put("message", message);
            peer.put("owner", node);
            node.put("peer", peer);
            retained.addLast(node);
            if (retained.size() > retainLimit) { retained.removeFirst(); evicted++; }
        }
        writer.write((Json.stringify(message) + "\n").getBytes(StandardCharsets.UTF_8));
        count++;
        totalCount++;
        if (count % flushEvery == 0) writer.flush();
        replies.write((message.get("id").toString() + "\n").getBytes(StandardCharsets.US_ASCII));
    }

    Map<String, Object> finish() throws IOException {
        if (finalMetrics != null) return finalMetrics;
        writer.flush();
        long endedNs = System.nanoTime(), cpuEndedNs = os.getProcessCpuTime();
        long endUptimeMs = runtime.getUptime();
        measuring = false;
        writer.close();
        finalMetrics = new LinkedHashMap<>();
        finalMetrics.put("control", "stop");
        finalMetrics.put("count", count);
        finalMetrics.put("total_count_including_warmup", totalCount);
        finalMetrics.put("retained", retained.size());
        finalMetrics.put("evicted", evicted);
        finalMetrics.put("elapsed_ns", startedNs == 0 ? null : endedNs - startedNs);
        finalMetrics.put("process_cpu_ns", startedNs == 0 ? null : cpuEndedNs - cpuStartedNs);
        finalMetrics.put("gc_window_start_uptime_ms", startUptimeMs);
        finalMetrics.put("gc_window_end_uptime_ms", endUptimeMs);
        finalMetrics.put("gc_stats_before", gcBefore);
        finalMetrics.put("gc_stats_after", gcStats());
        finalMetrics.put("java_version", Runtime.version().toString());
        finalMetrics.put("java_vendor", System.getProperty("java.vendor"));
        finalMetrics.put("jvm_flags", runtime.getInputArguments());
        finalMetrics.put("gc_names", collectors.stream().map(GarbageCollectorMXBean::getName).toList());
        return finalMetrics;
    }

    static Map<String, String> options(String[] argv) {
        Map<String, String> result = new HashMap<>();
        for (int i = 0; i < argv.length; i += 2) {
            if (!argv[i].startsWith("--") || i + 1 == argv.length) throw new IllegalArgumentException("use --key value");
            result.put(argv[i].substring(2), argv[i + 1]);
        }
        return result;
    }

    public static void main(String[] argv) throws Exception {
        Map<String, String> args = options(argv);
        Handler handler = new Handler(args);
        boolean stopping = false;
        try (ServerSocket server = new ServerSocket()) {
            server.setReuseAddress(true);
            server.bind(new InetSocketAddress(args.getOrDefault("host", "127.0.0.1"),
                        Integer.parseInt(args.getOrDefault("port", "9000"))), 16);
            System.out.println(Json.stringify(Map.of("ready", true, "port", server.getLocalPort(), "application_threads", 1L)));
            System.out.flush();
            while (!stopping) {
                try (Socket connection = server.accept()) {
                    connection.setTcpNoDelay(true);
                    LineReader reader = new LineReader(connection.getInputStream(), handler.bufferBytes, handler.maxMessageBytes);
                    OutputStream replies = connection.getOutputStream();
                    String line;
                    while ((line = reader.readLine()) != null) {
                        Map<String, Object> message = parseMessage(line);
                        if (message.containsKey("_control")) {
                            Object command = message.get("_control");
                            Map<String, Object> reply;
                            if ("begin".equals(command)) reply = handler.begin();
                            else if ("stop".equals(command)) { reply = handler.finish(); stopping = true; }
                            else throw new IllegalArgumentException("unknown control");
                            replies.write((Json.stringify(reply) + "\n").getBytes(StandardCharsets.UTF_8));
                        } else handler.handle(line, message, replies);
                        if (stopping) break;
                    }
                }
            }
        } finally {
            System.out.println(Json.stringify(handler.finish()));
            System.out.flush();
        }
    }

    static final class LineReader {
        final BufferedInputStream input;
        final int maximum;
        final CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT);
        byte[] line = new byte[1024];
        LineReader(InputStream input, int bufferBytes, int maximum) {
            this.input = new BufferedInputStream(input, bufferBytes);
            this.maximum = maximum;
        }
        String readLine() throws IOException {
            int length = 0;
            for (;;) {
                int value = input.read();
                if (value == -1) {
                    if (length == 0) return null;
                    throw new IOException("unterminated message");
                }
                if (value == '\n') return decoder.reset().decode(ByteBuffer.wrap(line, 0, length)).toString();
                if (length >= maximum) throw new IOException("oversized message");
                if (length == line.length) line = Arrays.copyOf(line, Math.min(maximum, line.length * 2));
                line[length++] = (byte) value;
            }
        }
    }

    /** JSON trees using standard-library collections; common numeric/Unicode domain. */
    static final class Json {
        final String text;
        int position;
        Json(String text) { this.text = text; }
        static Object parse(String text) {
            Json parser = new Json(text);
            Object value = parser.value(0);
            parser.whitespace();
            if (parser.position != text.length()) throw parser.error("trailing input");
            return value;
        }
        IllegalArgumentException error(String reason) { return new IllegalArgumentException(reason + " at " + position); }
        void whitespace() {
            while (position < text.length() && " \t\r\n".indexOf(text.charAt(position)) >= 0) position++;
        }
        boolean consume(char ch) {
            if (position < text.length() && text.charAt(position) == ch) { position++; return true; }
            return false;
        }
        void require(char ch) { if (!consume(ch)) throw error("expected " + ch); }
        Object value(int depth) {
            if (depth > 64) throw error("JSON nesting exceeds 64");
            whitespace();
            if (position >= text.length()) throw error("missing value");
            char ch = text.charAt(position);
            if (ch == '"') return string();
            if (ch == '{') {
                position++;
                Map<String, Object> result = new LinkedHashMap<>();
                whitespace();
                if (consume('}')) return result;
                do {
                    whitespace();
                    if (position >= text.length() || text.charAt(position) != '"') throw error("missing object key");
                    String key = string();
                    whitespace(); require(':');
                    result.put(key, value(depth + 1));
                    whitespace();
                    if (consume('}')) return result;
                    require(',');
                } while (true);
            }
            if (ch == '[') {
                position++;
                List<Object> result = new ArrayList<>();
                whitespace();
                if (consume(']')) return result;
                do {
                    result.add(value(depth + 1));
                    whitespace();
                    if (consume(']')) return result;
                    require(',');
                } while (true);
            }
            if (ch == 't' && text.startsWith("true", position)) { position += 4; return true; }
            if (ch == 'f' && text.startsWith("false", position)) { position += 5; return false; }
            if (ch == 'n' && text.startsWith("null", position)) { position += 4; return null; }
            return number();
        }
        String string() {
            require('"');
            StringBuilder result = new StringBuilder();
            boolean closed = false;
            while (position < text.length()) {
                char ch = text.charAt(position++);
                if (ch == '"') { closed = true; break; }
                if (ch < 32) throw error("unescaped control character");
                if (ch == '\\') {
                    if (position == text.length()) throw error("incomplete escape");
                    char escape = text.charAt(position++);
                    ch = switch (escape) {
                        case '"', '\\', '/' -> escape;
                        case 'b' -> '\b'; case 'f' -> '\f'; case 'n' -> '\n';
                        case 'r' -> '\r'; case 't' -> '\t';
                        case 'u' -> {
                            if (position + 4 > text.length()) throw error("incomplete unicode escape");
                            int code = 0;
                            for (int i = 0; i < 4; i++) {
                                char hex = text.charAt(position++);
                                int digit = hex <= 127 ? Character.digit(hex, 16) : -1;
                                if (digit < 0) throw error("invalid unicode escape");
                                code = code * 16 + digit;
                            }
                            yield (char) code;
                        }
                        default -> throw error("invalid escape");
                    };
                }
                result.append(ch);
            }
            if (!closed) throw error("unterminated string");
            for (int i = 0; i < result.length(); i++) {
                char ch = result.charAt(i);
                if (Character.isHighSurrogate(ch)) {
                    if (++i >= result.length() || !Character.isLowSurrogate(result.charAt(i))) throw error("unpaired surrogate");
                } else if (Character.isLowSurrogate(ch)) throw error("unpaired surrogate");
            }
            return result.toString();
        }
        boolean digit() { return position < text.length() && text.charAt(position) >= '0' && text.charAt(position) <= '9'; }
        void digits() { if (!digit()) throw error("missing digit"); while (digit()) position++; }
        Object number() {
            int start = position;
            consume('-');
            if (!consume('0')) digits();
            boolean floating = false;
            if (consume('.')) { floating = true; digits(); }
            if (consume('e') || consume('E')) { floating = true; if (!consume('+')) consume('-'); digits(); }
            String token = text.substring(start, position);
            if (floating) {
                double number = Double.parseDouble(token);
                if (!Double.isFinite(number)) throw error("non-finite JSON number");
                return number;
            }
            long number = Long.parseLong(token);
            if (number < -MAX_INTEGER || number > MAX_INTEGER) throw error("integer outside common exact range");
            return number;
        }
        static String stringify(Object value) {
            StringBuilder result = new StringBuilder();
            write(value, result);
            return result.toString();
        }
        static void write(Object value, StringBuilder result) {
            if (value == null) result.append("null");
            else if (value instanceof String text) quote(text, result);
            else if (value instanceof Number || value instanceof Boolean) result.append(value);
            else if (value instanceof Map<?, ?> map) {
                result.append('{');
                boolean first = true;
                for (Map.Entry<?, ?> entry : map.entrySet()) {
                    if (!first) result.append(','); first = false;
                    quote((String) entry.getKey(), result); result.append(':'); write(entry.getValue(), result);
                }
                result.append('}');
            } else if (value instanceof Iterable<?> list) {
                result.append('[');
                boolean first = true;
                for (Object item : list) {
                    if (!first) result.append(','); first = false; write(item, result);
                }
                result.append(']');
            } else throw new IllegalArgumentException("unsupported JSON value " + value.getClass());
        }
        static void quote(String text, StringBuilder result) {
            result.append('"');
            for (int i = 0; i < text.length(); i++) {
                char ch = text.charAt(i);
                switch (ch) {
                    case '"' -> result.append("\\\""); case '\\' -> result.append("\\\\");
                    case '\b' -> result.append("\\b"); case '\f' -> result.append("\\f");
                    case '\n' -> result.append("\\n"); case '\r' -> result.append("\\r"); case '\t' -> result.append("\\t");
                    default -> {
                        if (ch < 32) {
                            result.append("\\u00");
                            result.append("0123456789abcdef".charAt(ch >>> 4));
                            result.append("0123456789abcdef".charAt(ch & 15));
                        } else result.append(ch);
                    }
                }
            }
            result.append('"');
        }
    }
}
