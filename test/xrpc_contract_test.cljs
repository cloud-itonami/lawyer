#!/usr/bin/env nbb
;; test/xrpc_contract_test.cljs — do the lexicons, the deployed route, the views
;; and the README still agree about this app's XRPC surface?
;;
;; The README calls `lexicons/lawyer/` the "NSID contract SSoT". Four other
;; files restate parts of that contract, and **nothing read them together**:
;;
;;   - `worker/svelte/src/routes/xrpc/[...path]/+server.ts` — the route that is
;;     actually deployed (wrangler.jsonc points at the SvelteKit build output).
;;   - the four `.svelte` views, which name NSIDs as string literals.
;;   - `worker/src/app.ts`, whose `/health` payload advertises a command list.
;;   - the README's own XRPC table, which repeats every NSID *and its type*.
;;
;; TypeScript cannot connect any of these. The NSIDs are string literals, the
;; lexicon types live in JSON, and the route's handlers are exported symbols —
;; `tsc --noEmit` and `svelte-check` both pass while the four disagree.
;;
;; ## The binding this pins
;;
;; XRPC (AT Protocol) binds a lexicon's `type` to an HTTP method: a `query` is
;; fetched with GET and its parameters ride in the query string; a `procedure`
;; is POSTed with a JSON body. So a lexicon that declares `query` is a claim
;; about the route — it says a GET handler exists — and the views act on that
;; claim by calling `fetch(url)` with no options.
;;
;; A route that exports no GET returns 405 to every one of them. The views each
;; wrap that call in `try { … } catch { …DEMO… }`, so the failure does not
;; surface as an error: the page renders **fabricated matters and grants** and
;; nothing on screen says so. That is the specific shape this file exists to
;; keep from coming back — a broken contract that looks like working software.
;;
;; ## Exit codes — "could not measure" is not "measured clean"
;;
;;   0  every invariant held, on a non-empty surface
;;   1  an invariant was violated (the message names which, and what to look at)
;;   2  REFUSED — an input could not be read, so no claim is made
;;
;; Exit 2 exists because the cheapest way to write this check wrong is to let a
;; missing lexicon directory or an unreadable route fall through the same `seq`
;; as a clean one and print OK (CLAUDE.md: 入力が無いとき何を返すか。pass なら
;; それが欠陥).
;;
;; Usage:  nbb test/xrpc_contract_test.cljs

(ns xrpc-contract-test
  (:require ["node:fs" :as fs]
            ["node:path" :as path]
            [clojure.string :as str]))

(def root
  (path/resolve (path/dirname (or js/__filename "test/xrpc_contract_test.cljs")) ".."))

(defn- abs [rel] (path/join root rel))
(defn- slurp* [rel]
  (let [p (abs rel)]
    (when (fs/existsSync p) (str (fs/readFileSync p "utf8")))))

(def failures (atom []))
(defn- fail! [invariant detail] (swap! failures conj (str "FAIL " invariant ": " detail)))

(defn- refuse! [why]
  (println (str "REFUSED " why))
  (println "lawyer contracts: no claim made — an input could not be read.")
  (js/process.exit 2))

;; ── inputs ──────────────────────────────────────────────────────────────────

(def lexicon-dir "lexicons/lawyer")
(def route-file "worker/svelte/src/routes/xrpc/[...path]/+server.ts")
(def facade-file "worker/src/app.ts")
(def views-dir "worker/svelte/src/routes")

(def nsid-prefix "ai.gftd.apps.lawyer.")

(when-not (fs/existsSync (abs lexicon-dir))
  (refuse! (str lexicon-dir " does not exist — the NSID contract SSoT is gone")))

(def lexicons
  (let [names (->> (fs/readdirSync (abs lexicon-dir))
                   (map str)
                   (filter #(str/ends-with? % ".json"))
                   sort vec)]
    (when (empty? names)
      (refuse! (str lexicon-dir " holds no .json — nothing to check against")))
    (vec (for [n names]
           (let [rel  (str lexicon-dir "/" n)
                 text (or (slurp* rel) (refuse! (str "cannot read " rel)))
                 j    (try (js/JSON.parse text)
                           (catch :default e
                             (refuse! (str rel " is not parseable JSON: " (.-message e)))))
                 id   (some-> (aget j "id") str)
                 typ  (some-> j (aget "defs") (aget "main") (aget "type") str)]
             (when-not id   (refuse! (str rel " has no top-level \"id\"")))
             (when-not typ  (refuse! (str rel " has no defs.main.type")))
             {:file rel :basename (subs n 0 (- (count n) 5)) :id id :type typ})))))

(def route-src (or (slurp* route-file)
                   (refuse! (str route-file " is missing — it is what wrangler deploys"))))
(def facade-src (or (slurp* facade-file) (refuse! (str facade-file " is missing"))))
(def readme (or (slurp* "README.md") (refuse! "README.md is missing")))

(def view-files
  (let [walk (fn walk [dir]
               (mapcat (fn [e]
                         (let [p (path/join dir (str (.-name e)))]
                           (cond (.isDirectory e) (walk p)
                                 (str/ends-with? (str (.-name e)) ".svelte") [p]
                                 :else [])))
                       (fs/readdirSync dir #js {:withFileTypes true})))]
    (if (fs/existsSync (abs views-dir))
      (vec (sort (map #(path/relative root %) (walk (abs views-dir)))))
      (refuse! (str views-dir " does not exist — there are no views to check")))))

(when (empty? view-files)
  (refuse! (str views-dir " holds no .svelte files")))

;; ── what the route actually exports ─────────────────────────────────────────
;;
;; SvelteKit dispatches on the exported symbol name: a request method with no
;; matching export gets 405 from the framework, before any of this file's code
;; runs. So the set of exported names IS the set of methods the route answers.

(def exported-methods
  (into #{} (map second) (re-seq #"(?m)^export\s+const\s+([A-Z]+)\s*:" route-src)))

;; XRPC's lexicon-type -> HTTP-method binding. Not a preference: it is how a
;; caller that reads only the lexicon decides how to call.
(def method-for-type {"query" "GET" "procedure" "POST"})

;; ── invariants ──────────────────────────────────────────────────────────────

;; 1. A lexicon's id is derived from its path by every consumer that globs this
;;    directory; a rename that moves only the file leaves the id behind.
(doseq [{:keys [file basename id]} lexicons]
  (let [expect (str nsid-prefix basename)]
    (when-not (= id expect)
      (fail! "lexicon-id-matches-filename"
             (str file " declares id " (pr-str id) ", but its path says " (pr-str expect))))))

;; 2. Every declared type must be reachable on the deployed route.
;;    This is the one that catches a surface which typechecks and deploys and
;;    still answers 405 to a third of itself.
(doseq [[typ ids] (->> lexicons (group-by :type) (sort-by key))]
  (if-let [needed (method-for-type typ)]
    (when-not (exported-methods needed)
      (fail! "every-declared-method-type-is-reachable"
             (str (count ids) " lexicon(s) declare type " (pr-str typ)
                  " — XRPC binds that to HTTP " needed
                  " — but " route-file " exports only "
                  (str/join "," (sort exported-methods))
                  ". Unreachable: " (str/join ", " (sort (map :id ids)))
                  ". Callers: " (str/join ", "
                                          (sort (for [v view-files
                                                      :let [t (slurp* v)]
                                                      :when (some #(str/includes? t (:id %)) ids)]
                                                  v))))))
    (fail! "every-declared-method-type-is-reachable"
           (str "lexicon type " (pr-str typ) " has no known HTTP binding; "
                "seen in " (str/join ", " (sort (map :file ids)))))))

;; 3. CORS preflight must advertise every method the route exports, or a
;;    cross-origin caller is refused by the browser before the route is reached.
(when (exported-methods "OPTIONS")
  (if-let [[_ advertised] (re-find #"'access-control-allow-methods':\s*'([^']*)'" route-src)]
    (let [adv (into #{} (map str/trim) (str/split advertised #","))
          missing (remove adv (disj exported-methods "OPTIONS"))]
      (when (seq missing)
        (fail! "cors-advertises-every-exported-method"
               (str route-file " exports " (str/join "," (sort missing))
                    " but its preflight advertises only " (pr-str advertised)))))
    (fail! "cors-advertises-every-exported-method"
           (str route-file " exports OPTIONS but sets no access-control-allow-methods"))))

;; 4. Every NSID named anywhere in the deployed worker must be declared. A typo
;;    or a half-finished rename is a 502 at runtime and nothing at build time.
(def declared-ids (into #{} (map :id) lexicons))

(def referenced
  (into {}
        (for [f (conj view-files facade-file)
              :let [t (or (slurp* f) "")
                    ;; No capture group in this pattern, so re-seq yields the
                    ;; matched strings themselves — do not map `first` over them.
                    ids (into #{} (re-seq (re-pattern (str nsid-prefix "[A-Za-z0-9]+")) t))]
              :when (seq ids)]
          [f ids])))

(doseq [[f ids] (sort referenced)
        id (sort ids)]
  (when-not (declared-ids id)
    (fail! "every-referenced-nsid-is-declared"
           (str f " names " (pr-str id) ", which no lexicon in " lexicon-dir " declares"))))

;; 5. The /health payload advertises a command list. It is a declaration about
;;    this app made to whoever polls it, and it is written by hand.
(when-let [[_ block] (re-find #"(?s)commands:\s*\[(.*?)\]" facade-src)]
  (let [advertised (into #{} (map second) (re-seq #"\"([^\"]+)\"" block))]
    (doseq [id (sort advertised)]
      (when-not (declared-ids id)
        (fail! "advertised-commands-are-declared"
               (str facade-file " advertises " (pr-str id) " in its /health commands, "
                    "which no lexicon declares"))))
    (doseq [id (sort (remove advertised declared-ids))]
      (fail! "advertised-commands-are-declared"
             (str facade-file " does not advertise " (pr-str id)
                  ", which " lexicon-dir " declares")))))

;; 6. The README repeats every NSID *and its type*. That table is the version a
;;    reader trusts, and it is the copy most likely to be left behind.
(let [rows (re-seq #"(?m)^\|\s*`([A-Za-z0-9]+)`\s*\|\s*(query|procedure)\s*\|" readme)]
  (if (empty? rows)
    (refuse! "README.md has no XRPC table rows (| `nsid` | query|procedure |) — cannot compare")
    (let [by-name (into {} (map (fn [[_ n t]] [n t])) rows)]
      (doseq [{:keys [basename type id]} lexicons]
        (if-let [t (by-name basename)]
          (when-not (= t type)
            (fail! "readme-table-matches-lexicons"
                   (str "README lists " basename " as " (pr-str t)
                        " but " id " declares " (pr-str type))))
          (fail! "readme-table-matches-lexicons"
                 (str "README's XRPC table omits " (pr-str id)))))
      (doseq [n (sort (remove (into #{} (map :basename) lexicons) (keys by-name)))]
        (fail! "readme-table-matches-lexicons"
               (str "README's XRPC table lists " (pr-str n) ", which no lexicon declares"))))))

;; ── report ──────────────────────────────────────────────────────────────────

(println (str "SCANNED\tlexicons=" (count lexicons)
              "\tqueries=" (count (filter #(= "query" (:type %)) lexicons))
              "\tprocedures=" (count (filter #(= "procedure" (:type %)) lexicons))
              "\troute-methods=" (str/join "," (sort exported-methods))
              "\tview-files=" (count view-files)
              "\tfiles-naming-an-nsid=" (count referenced)))

(if (seq @failures)
  (do (doseq [f @failures] (println f))
      (println (str "lawyer contracts: " (count @failures) " invariant(s) violated"))
      (js/process.exit 1))
  (do (println "lawyer contracts: all green")
      (js/process.exit 0)))
