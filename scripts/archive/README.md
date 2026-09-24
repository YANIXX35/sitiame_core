# Scripts archivés

Scripts ponctuels déjà exécutés en production, gardés pour l'historique.
Ils sont volontairement **hors du paquet `sitiame_core/`** : `bench execute`
ne peut pas les appeler, donc personne ne peut les relancer par erreur.

## 2026-09-24_fix_all_companies_syscohada.py

Migration SYSCOHADA (procédure F-45), exécutée le 2026-09-24 vers 13:07 sur
toutes les sociétés d'erp.sitiame-capital.com.

**Ne pas relancer tel quel.** Pour toute société qui n'a encore aucune
écriture (GL Entry), il **supprime entièrement le plan comptable** puis le
régénère depuis « Syscohada - Plan Comptable avec code ».

Les nouvelles sociétés n'en ont pas besoin : `_apply_syscohada_defaults`
(`sitiame_core/api.py`) applique déjà ces corrections à l'inscription.
