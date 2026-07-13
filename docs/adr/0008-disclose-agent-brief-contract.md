# Disclose Agent Brief Contract

`$ultra-to-tickets` should keep its wrapper body thin and point to the Agent Brief reference when it publishes ready-for-agent tickets. The wrapper remains an adapter around the external `to-tickets` skill, while the reference owns local ticket-shaping expectations such as stable context, constraints, validation expectations, optional hints, and the rule that `/ultra solve` treats the brief as preferred input rather than a schema gate.
