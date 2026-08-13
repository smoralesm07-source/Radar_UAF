# Contrato de interoperabilidad de radares v1

Este directorio define la capa transversal de interoperabilidad. No reemplaza el modelo interno del radar ni modifica sus algoritmos, scores o dashboard.

## Principios

1. **Entidad común (Entity Hub).** Una persona jurídica chilena con RUT válido usa `entity_id = ENT-RUT-{RUT_NORMALIZADO}`. El rol se modela aparte y nunca crea una identidad distinta.
2. **Sin RUT válido no se fuerza identidad global.** `entity_id` permanece `null`; los matches por nombre son candidatos con método y confianza.
3. **Territorio común.** Región y comuna se identifican por códigos oficiales (`CL-REG-*`, `CL-COM-*`), no por nombres libres.
4. **Sector común.** La homologación Ley 19.913 ↔ SII distingue `VALIDATED_EXACT`, `VALIDATED_RULE`, `EMPIRICAL_CANDIDATE`, `AMBIGUOUS` y `NO_EQUIVALENCE`.
5. **Tiempo y evidencia.** Se separan fecha observada, publicación, recuperación y última actualización exitosa. Falla de fuente ≠ cero y una actualización fallida no borra el último dato válido.
6. **Scores no comparables.** Cada radar conserva su propio score, alcance y versión. No existe un `risk_score` transversal en v1.

`integration_manifest_v1.json` describe cómo este radar se integra al sistema y `interop_contract_v1.schema.json` fija el contrato declarativo común.