extends SceneTree
## Test du client Godot — D2 et D3.
##
## Deux modes, dans le même fichier :
##
##   godot --headless --path godot/project --script res://tests/test_client.gd
##       vérifie les **gestionnaires de trames** sur des messages fabriqués :
##       rien n'est simulé, mais tout le contrat JSON est exercé. C'est le
##       test qui casse si `snapshot.memory` ou `world.announcement` change
##       de forme.
##
##   MAREE_TEST_LIVE=1 godot --headless --path godot/project \
##       --script res://tests/test_client.gd
##       suppose un `maree live` sur ws://127.0.0.1:8765. Il clique
##       « Annoncer », attend l'`ack`, l'écho `injection` et la trame
##       `world` — c'est-à-dire le trajet complet d'une injection D3.
##
## Sortie : 0 si tout passe, 1 sinon (utilisable dans un make).

var _failures: Array[String] = []
var _checks := 0


func _initialize() -> void:
	if OS.get_environment("MAREE_TEST_LIVE") == "1":
		await _live()
	else:
		# Hors-ligne : fermer le port avant `_ready` pour ne pas injecter
		# par accident dans un `maree live` qui tournerait à côté.
		OS.set_environment("MAREE_WS_URL", "ws://127.0.0.1:1")
		await _offline()
	_report()


func _check(ok: bool, label: String) -> void:
	_checks += 1
	if ok:
		print("  ok   %s" % label)
	else:
		_failures.append(label)
		print("  FAIL %s" % label)


func _report() -> void:
	print("%d vérifications, %d échec(s)" % [_checks, _failures.size()])
	quit(1 if _failures.size() > 0 else 0)


# ------------------------------------------------------------------
# Hors-ligne : les gestionnaires, sans serveur
# ------------------------------------------------------------------
func _offline() -> void:
	var main = load("res://scenes/main.tscn").instantiate()
	root.add_child(main)
	# `_ready` (donc la construction de l'interface) a lieu à l'entrée
	# dans l'arbre, pas à l'instanciation.
	await process_frame

	# hello : le plan, et le fait qu'on est en rejeu.
	main._handle(JSON.stringify({
		"type": "hello",
		"run_id": "test",
		"live": false,
		"plan": {
			"width": 60.0,
			"height": 40.0,
			"walkable": [[0.0, 0.0], [60.0, 0.0], [60.0, 40.0], [0.0, 40.0]],
			"obstacles": [],
			"exits": [{"id": "A", "a": [0.0, 2.0], "b": [2.0, 2.0]}],
		},
	}))
	_check(not main._plan.is_empty(), "hello : plan reçu")
	_check(main._live == false, "hello.live=false reconnu")
	# D3 — en rejeu on n'offre pas un bouton qui sera refusé.
	_check(main._buttons[0].disabled, "rejeu : boutons d'injection désactivés")
	_check("rejeu" in main._hint.text, "rejeu : la raison est affichée")

	# snapshot : D2 doit recevoir mémoire + décision + règle.
	main._handle(JSON.stringify({
		"type": "snapshot",
		"tick": 12,
		"sim_time": "2:00",
		"exits_open": ["A"],
		"smoke_active": true,
		"smoke": {"position": [10.0, 20.0], "radius": 5.0, "tick": 10},
		"announcement": null,
		"density_grid": [{"x": 8.0, "y": 30.0, "n": 2}],
		"agents": [{
			"id": "A01",
			"profile": "vendeur",
			"label": "Commerçant",
			"kind": "rules",
			"pos": [10.0, 20.0],
			"belief": "B",
			"confidence": 0.6,
			"beliefs": {"A": {"confidence": 0.4, "source": "connu", "tick": 0}},
			"entropy": 0.7,
			"intention": "guide",
			"intention_target": "A",
			"evacuated": false,
			"kin": null,
			"decided_at": 10,
			"perceived": ["smoke"],
			"memory": [{
				"tick": -25920,
				"kind": "briefing",
				"content": "la sortie B se bouche les jours de marché",
				"source": "prehistoire",
				"salience": 0.5,
				"tags": [],
			}],
			"last_decision": {
				"tick": 10,
				"kind": "rules",
				"trigger": "fumee_visible",
				"reason": "orienter vers A : A minimise distance + densité",
				"rule": "orienter vers A : A minimise distance + densité",
				"intention": {"kind": "guide", "target": "A"},
				"retrieved": [],
				"memory": [],
			},
		}],
	}))
	var agent: Dictionary = main._agent_by_id("A01")
	_check(not agent.is_empty(), "snapshot : l'agent est là")
	_check(agent.get("memory", []).size() == 1, "D2 : la mémoire arrive")
	_check(
		agent.get("last_decision", {}).get("rule", null) != null,
		"D2 : la règle appliquée arrive",
	)
	_check(
		str(agent.get("last_decision", {}).get("reason", "")) != "",
		"D2 : la justification arrive",
	)
	_check(main._when(-25920) == "J-3", "D2 : la préhistoire se lit J-3")
	# D1 — l'écart avec la réalité est calculable pour chaque agent :
	# il croit B, seule A est ouverte.
	_check(not main._is_open(str(agent.get("belief"))), "D1 : croyance fermée détectée")
	_check(main._snap["density_grid"].size() == 1, "D1 : la grille de densité arrive")

	# world : la fumée et l'annonce ne passent que par là.
	main._handle('{"type":"world","kind":"smoke","position":[10,20],"radius":5.0,"tick":14}')
	_check(float(main._world_smoke.get("radius", 0.0)) == 5.0, "D3 : trame world smoke")
	main._handle('{"type":"world","kind":"announcement","text":"Évacuez par B"}')
	_check(main._announcement == "Évacuez par B", "D3 : trame world announcement")

	# live=true rallume les commandes ; une trame inconnue est signalée.
	main._handle('{"type":"hello","live":true,"plan":{"height":40.0}}')
	_check(not main._buttons[0].disabled, "live : boutons d'injection actifs")
	main._handle('{"type":"error","reason":"run en rejeu : aucune injection possible"}')
	_check("aucune injection" in main._hint.text, "D3 : l'erreur serveur est affichée")

	main.queue_free()


# ------------------------------------------------------------------
# En ligne : le trajet complet d'une injection
# ------------------------------------------------------------------
func _live() -> void:
	var main = load("res://scenes/main.tscn").instantiate()
	root.add_child(main)
	await process_frame

	var ok := await _wait_for(func() -> bool:
		return main._ws.get_ready_state() == WebSocketPeer.STATE_OPEN, 8.0)
	_check(ok, "connexion au serveur")

	ok = await _wait_for(func() -> bool: return not main._plan.is_empty(), 8.0)
	_check(ok, "hello : plan reçu")
	_check(main._live, "hello.live=true (mode direct)")
	_check(not main._buttons[0].disabled, "boutons d'injection actifs")

	ok = await _wait_for(func() -> bool:
		return not main._snap.is_empty() and main._snap.get("agents", []).size() > 0, 8.0)
	_check(ok, "instantané peuplé reçu")

	# D3 — le clic sur « Annoncer » part réellement sur la socket.
	main._announce_edit.text = "Évacuation immédiate, sortie B"
	main._inject_announcement()
	ok = await _wait_for(func() -> bool: return "✔" in main._hint.text, 8.0)
	_check(ok, "ack reçu du serveur")
	ok = await _wait_for(func() -> bool: return "injecté" in main._hint.text, 8.0)
	_check(ok, "écho control.injection reçu (trame injection)")
	ok = await _wait_for(func() -> bool:
		return main._announcement == "Évacuation immédiate, sortie B", 10.0)
	_check(ok, "trame world announcement reçue et affichée")
	ok = await _wait_for(func() -> bool:
		return str(main._snap.get("announcement", "")) == "Évacuation immédiate, sortie B", 10.0)
	_check(ok, "l'annonce persiste dans l'instantané (client tardif)")

	# D2 — un agent réel porte mémoire et décision.
	ok = await _wait_for(func() -> bool:
		for a in main._snap.get("agents", []):
			if not a.get("memory", []).is_empty() and a.get("last_decision") != null:
				return true
		return false, 15.0)
	_check(ok, "D2 : un agent réel expose mémoire + dernière décision")

	main.queue_free()


func _wait_for(predicate: Callable, timeout_s: float) -> bool:
	var waited := 0.0
	while waited < timeout_s:
		if predicate.call():
			return true
		await create_timer(0.1).timeout
		waited += 0.1
	return predicate.call()
