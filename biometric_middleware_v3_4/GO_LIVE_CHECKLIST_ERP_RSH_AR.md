<div dir="rtl" align="right">

# قائمة التحقق للإطلاق — Biometric Attendance (ERP / RSH)

**المشروع:** Raidat — Odoo 16 + Windows Biometric Middleware

**تاريخ إنشاء القائمة:** 2026-10-20

**حالة الإطلاق:** غير جاهز — لا يوجد اعتماد على Production.

**المصدر المعتمد لهذه القائمة:** فحوصات SSH وWindows المثبتة أثناء متابعة المشروع، ومراجعة كود Odoo وMiddleware بتاريخ 2026-10-20.

> **قاعدة العمل:** نجاح Test Case على Staging لا يعني أن إعدادها موجود على Live. لكل بند حالة اختبار، وإجراء نقل/تهيئة للإنتاج، ثم دليل تحقق من Live. لا تُكتب أسرار الاتصال في هذا الملف ولا في Git.

## طريقة تحديث القائمة بعد كل Test Case

1. اكتب رقم الاختبار، وتاريخ التنفيذ، والبيئة، والنتيجة: `PASS` أو `FAIL` أو `BLOCKED`.
2. أرفق الدليل المناسب: Screenshot أو Log منقح أو SQL Read-Only أو نتيجة HTTP، مع إخفاء كلمات المرور وAPI Tokens والبيانات الشخصية.
3. اكتب جميع الإعدادات اللازمة عند النقل إلى Production، بما فيها أي تعديل جرى من Odoo UI ولم يُسجل في الكود.
4. اكتب خطوة التحقق المقابلة على ERP Live أو RSH Live، ولا تُعلّم `Live verified` قبل تنفيذها فعليًا.
5. أي تغيير جديد في الإعدادات أو الكود أو البيانات يتطلب تحديث رقم الإصدار ومصفوفة التحقق.
6. لا يتم اعتماد Go-Live إلا بعد توقيع المسؤول عن الاختبار ومسؤول الإنتاج ومراجعة خطة التراجع.

**المفاتيح:** `[x]` تحقق فعليًا؛ `[ ]` لم يتحقق بعد؛ `BLOCKED` يتطلب حل مانع؛ `N/A` غير منطبق بعد توثيق السبب.

## 1) خط الأساس المثبت — لا يُعتبر جاهزية إنتاج

| المعرف | البيئة / العنصر | الحالة المثبتة | الناقص |
|---|---|---|---|
| BASE-01 | ERP Live: `erp.raidatalsharq.com` | موديولات `rgb_biometric_attendance_bridge` و`rgb_biometric_first_last_attendance` مثبتة؛ جهازان نشطان؛ 2,052 Raw Events وقت الفحص | Cron متوقف عمليًا؛ 60 Raw Events جديدة عند الفحص؛ التحقق من بقية أحداث اليوم |
| BASE-02 | RSH Live: `rsh.raidatalsharq.com` | `hr_attendance` مثبت | موديولات البصمة وتهيئة الأجهزة والموظفين غير مثبتة/مكتملة |
| BASE-03 | RSH Test: `test_RSH` | الموديولات مثبتة؛ SQL قبل التهيئة: 0 Devices / 0 Mappings / 0 Raw Events. تنفيذ Odoo Shell بتاريخ 2026-10-20 أكد إنشاء Device Records اثنين | التحقق المستقل من الجهازين والـToken، واستكمال Employee Mappings، مع بقاء Cron بدون تغيير |
| BASE-04 | RSH Test: `asg_biometric_first_last.timezone` | تم تأكيد القيمة `Asia/Riyadh` عبر SQL | تأكيد نفس القيمة بشكل مستقل على RSH Live |
| BASE-05 | RSH Test: `asg_biometric.api_token` | آخر فحص SQL قبل التهيئة: غير موجود؛ أداة التهيئة أكدت توليد Token خاص بتاريخ 2026-10-20 | تحقق SQL/ORM مستقل من ضبطه ثم اختبار API دون عرضه في المخرجات |
| BASE-06 | ERP Test: `test` | قاعدة مشابهة لنسخة ERP Live؛ `hr_attendance` موجود | تأكيد عنوان الوصول والخدمة المنفصلة؛ تثبيت موديولات البصمة واختبارها |
| BASE-07 | Windows: `DESKTOP-FBHPKOK` | `RaidatBiometricConnector` تعمل تلقائيًا بواسطة NSSM / Python؛ timezone `Arab Standard Time` | لا تغير إعداداتها الحالية قبل اختبار النسخة الجديدة |
| BASE-08 | SQLite الحالية | 4,336 حدثًا؛ 2,052 `synced`؛ 2,284 `ignored`؛ 0 `pending` و0 `failed` وقت الفحص | فحص ملاءمة الأحداث المتجاهلة لتسليم RSH، وفحص أحداث لم تُخزَّن أصلًا |
| BASE-09 | SQLite Backup | `C:\RaidatBiometric\backups\middleware_20261020_020225.db`؛ `PRAGMA integrity_check = ok`؛ الأعداد مطابقة | اختبار Restoration عمليًا على نسخة معزولة؛ إنشاء Backup جديد قبل التحويل الفعلي |
| BASE-10 | Middleware Dev | `feature/biometric-multi-target`؛ `3.6.0`؛ 53 اختبارًا محليًا ناجحًا | اختبار End-to-End على Test؛ عدم نشره على Windows Production الآن |
| BASE-11 | Odoo Live Cron | `max_cron_threads=1`؛ عملية الإنتاج تُظهر خيطين مقابل 3 في Test؛ 28 مهمة متأخرة في ERP و26 في RSH | فحص/إصلاح Cron ضمن نافذة صيانة معتمدة؛ مراجعة قواعد الإنتاج الأخرى |
| BASE-12 | تشغيل المهام الموروثة | `Synced Attendance` موجودة على ERP/RSH؛ `EDI` لديها خطأ XML مستقل على ERP | التحقق من وظيفة `Synced Attendance` ومنع تعارض المعالجة؛ مراجعة المهام المالية قبل Restart |

**معلومة تشغيلية:** `ZKTeco / zk_room_1` يسحب كل 3,600 ثانية، و`Hikvision / hik_room_2` كل 300 ثانية؛ Middleware تعمل بشكل مستمر. المهمة اليومية الحالية لتحويل البصمات في ERP مضبوطة على 07:00 السعودية، لا على 06:15.

## 2) اختبار Staging — لا تبدأ Live قبل إغلاق جميع حالات المنع

### 2.1 بيئات الاختبار والكود

- [ ] **TC-ENV-01** — تأكيد الـDomain/Reverse Proxy وقاعدة `test` الخاصة بـERP، والخدمة المستقلة؛ عدم تمرير الطلبات بالخطأ إلى ERP Live.
- [ ] **TC-ENV-02** — تأكيد وصول `test_RSH` على Port 8070 عبر Host/Proxy الصحيح، وأن `dbfilter` و`db_name` يطابقان القاعدة.
- [ ] **TC-ENV-03** — مراجعة تطابق نسخ الكود الفعلية بين ERP Test وRSH Test ومصادر Git، وتوثيق commit لكل موديول.
- [ ] **TC-ENV-04** — تثبيت/تحديث `hr_attendance` و`rm_hr_attendance_sheet` و`rgb_biometric_attendance_bridge` و`rgb_biometric_first_last_attendance` على قواعد الاختبار المطلوبة.
- [ ] **TC-ENV-05** — تأكيد عدم وجود موديول قديم آخر يعالج نفس Raw Events أو Attendance بصورة متعارضة.

### 2.1.1 أداة تنفيذ تهيئة RSH Test — لا تُشغّل على Live

- [x] **TC-BOOT-UNIT-01** — تمت كتابة `scripts/bootstrap_rsh_test_odoo.py` على فرع التطوير؛ 3 اختبارات محلية تثبت منع قواعد غير `test_RSH`، وإنشاء الجهازين وSecret Mode 0600، ومنع تغيير Device متعارض.
- [x] **TC-BOOT-RSH-01** — تم التشغيل في Odoo Shell الخاصة بـ`test_RSH` بتاريخ 2026-10-20 بعد تحقق SHA/Git Hash للملف (`6522374d4cb7895f94e20d428820f492b3aa1f05`). المخرجات أكدت إنشاء `zk_room_1` و`hik_room_2` وToken Test خاص، مع عدم إنشاء Mappings وعدم تعديل Cron.
- [x] **TC-BOOT-RSH-02** — تحقق مستقل من Odoo Shell: جهازان (`hik_room_2` و`zk_room_1`) نشطان بـ`raw_only`، وToken مضبوط بطول مناسب، وEmployee Mappings = 0؛ قيمة `Asia/Riyadh` مثبتة بقراءة SQL سابقة؛ Cron لم يُعدّل بواسطة أداة التهيئة. مطلوب إعادة التحقق من Cron قبل الاختبار التشغيلي.
- [ ] **TC-BOOT-RSH-03** — حفظ API Token في ملف سري Mode 0600 وعدم إظهاره في Log أو إرسال قيمته في المحادثة؛ نسخه فقط إلى Runtime Test منعزل.
- [ ] **TC-BOOT-RSH-04** — مراجعة Mapping مع HR وإضافة روابط موظفي RSH بعد تأكيد External User IDs الفعلية، من دون نسخ Employee Record IDs من ERP.

**دليل التشغيل:** `scripts/bootstrap_rsh_test_odoo.py`، ويُنفّذ داخل Odoo Shell مع `env` على قاعدة `test_RSH` فقط، ولا يُشغّل بمجرد تحميل الملف. يجب تشغيله بواسطة مسؤول الاختبار مع Backup لقاعدة Test ومراجعة شركة RSH.

### 2.1.2 Employee Mapping — حالة بيانات RSH Test بتاريخ 2026-10-20

- [x] **TC-MAP-AUDIT-01** — Odoo Shell: 138 موظفًا نشطًا؛ `hr.employee.device_id` فارغ لجميعهم؛ `barcode` ممتلئ لـ9 موظفين؛ `pin` ممتلئ لـ137 موظفًا مع 136 قيمة مختلفة (أي قيمة مكررة). هذه معلومات فحص غير كافية لإثبات الربط مع الأجهزة.
- [x] **TC-MAP-SRC-01** — مراجعة Odoo 16: `hr.employee.pin` هو PIN أودو، و`barcode` بطاقة الموظف، وليس أي منهما مصدرًا مُعتمدًا افتراضيًا لـBiometric User ID؛ ممنوع إنشاء Mapping باستخدامه بلا مطابقة موثقة مع الجهاز.
- [x] **TC-MAP-DEV-01** — إنشاء `scripts/export_rsh_test_mapping_template.py` على فرع التطوير مع 3 اختبارات محلية؛ يولّد CSV خاصًا بصلاحية 0600 يحتوي على الموظفين النشطين في شركة RSH Test وأعمدة User ID للجهازين فارغة للمراجعة ولا يقرأ PINs.
- [ ] **TC-MAP-EXPORT-01** — تشغيل Exporter على `test_RSH` وإنشاء CSV خاص للـHR، وتأكيد عدد موظفي الشركة في الملف. لا رفع أو نشر ملف بيانات موظفين في Git أو في محادثات عامة.
- [ ] **TC-MAP-APPROVAL-01** — استلام قائمة Device User IDs الرسمية من مسؤول الأجهزة ومطابقتها بكل موظف لكل جهاز، واعتمادها من HR.
- [ ] **TC-MAP-IMPORT-01** — إعداد Importer آمن مع Preview + رفض التكرارات والغموض + تنفيذ Test فقط بموافقة صريحة. لا انتقال للـLive باستخدام `employee_id` الخاصة بـTest.
- [ ] **TC-MAP-API-01** — بعد الاستيراد: فحص `allowed-employees` لكل جهاز، والتأكد من عدم تمرير موظف غير مربوط في قاعدة RSH.

**ملاحظة:** الـCSV الخاص بـTest يحتوي على أسماء الموظفين؛ يُحفظ محليًا بإذن المالك فقط، ولا يُشارك داخل Git أو المحادثة. `employee_id` تخص بيئة Test فقط وقد تختلف عن Production.

### 2.2 Odoo Configuration — لكل قاعدة على حدة

- [ ] **TC-CFG-01** — قيمة `asg_biometric_first_last.timezone` تساوي `Asia/Riyadh` في ERP Test وRSH Test.
- [ ] **TC-CFG-02** — إنشاء `asg_biometric.api_token` مستقل وسري لكل قاعدة Test؛ التحقق من 401 عند Token خاطئ و200 عند Token صحيح.
- [ ] **TC-CFG-03** — إنشاء جهازين `asg.biometric.device` على كل قاعدة، بمعرفي `zk_room_1` و`hik_room_2` وأنواعهما الصحيحة؛ `active=True`؛ `company_id` الصحيحة.
- [ ] **TC-CFG-04** — ضبط `processing_strategy=raw_only` للجهازين؛ منع التحويل المزدوج من Bridge Cron.
- [ ] **TC-CFG-05** — تجهيز `asg.biometric.employee.mapping` بشكل مستقل لكل قاعدة اعتمادًا على `external_user_id` الفعلي على الجهاز، و`hr.employee` المطابق؛ الموظف مفعل؛ لا نسخ أرقام `employee_id` بين القواعد.
- [ ] **TC-CFG-06** — كشف التكرار أو الغموض في Mapping لكل Device؛ توثيق موظفي ERP فقط وRSH فقط والمشتركين.
- [ ] **TC-CFG-07** — تجربة `GET /biometric/api/v1/allowed-employees` لكل جهاز ولكل قاعدة؛ الرد يطابق Mapping ولا يمرر موظفي الشركة الأخرى.
- [ ] **TC-CFG-08** — تجربة `POST /biometric/api/v1/heartbeat` لكل قاعدة، وتحديث الجهاز الصحيح من غير تسريب بيانات.
- [ ] **TC-CFG-09** — تجربة `POST /biometric/api/v1/events` مع Accepted وIgnored وRejected وإعادة نفس `event_key` للتأكد من Idempotency.
- [ ] **TC-CFG-10** — تدقيق صلاحيات Odoo ومجموعات الوصول للقوائم والتقارير للـHR / Admin.

### 2.3 Middleware 3.6.0 — في Runtime منعزل عن خدمة Windows الحالية

- [x] **TC-MW-UNIT-01** — 53 اختبارًا محليًا ناجحًا؛ يشمل اختبارات مسارات تسليم ERP/RSH وأداة تهيئة RSH Test وقالب Employee Mapping الخاص بالاختبار (محاكاة وليست E2E).
- [ ] **TC-MW-01** — إنشاء Test Runtime وSQLite وConfig منفصلة كليًا عن Windows Production.
- [ ] **TC-MW-02** — التحقق من `legacy_target_id=erp` ومن تطابق ERP target URL مع `odoo.base_url` قبل ترحيل حالات SQLite.
- [ ] **TC-MW-03** — إثبات عدم إعادة إرسال سجلات ERP التي كانت `synced` عند ترقية السجل `event_deliveries`.
- [ ] **TC-MW-04** — لكل هدف سجل تسليم مستقل `event_deliveries`؛ رفض هدف/انقطاعه لا يغيّر حالات الهدف الآخر.
- [ ] **TC-MW-05** — تصفية جمع أحداث الجهاز باتحاد موظفي ERP وRSH، لكن إرسال كل حدث للقاعدة التي تحتوي على Mapping فقط.
- [ ] **TC-MW-06** — اختبار موظف RSH فقط وERP فقط وموظف موجود في القاعدتين، وعلى جهاز واحد أو جهازين.
- [ ] **TC-MW-07** — انقطاع API الخاص بـMapping لأي هدف يمنع تقديم Cursor الجهاز، ويتيح إعادة المحاولة لاحقًا بدون فقد.
- [ ] **TC-MW-08** — مراجعة `start_at` لكل وجهة جديدة؛ لا تاريخ افتراضي لنقل بيانات قديمة غير معتمدة.
- [ ] **TC-MW-09** — اختبار ترحيل وRollback بالاعتماد على نسخة SQLite مسترجعة في بيئة منفصلة؛ حالات ERP القديمة لا تتغير؛ منع إرسال Replay على Live أثناء الاختبار.
- [ ] **TC-MW-10** — مقارنة الأحداث `ignored` في ERP مع Mapping الخاصة بـRSH دون اعتبارها جميعًا تابعة لـRSH.
- [ ] **TC-MW-11** — تدقيق السجلات غير المحفوظة سابقًا بسبب فلتر ERP؛ دراسة Backfill من كل جهاز مع فحص فترة الاحتفاظ، وتحديد خطة آمنة لـHikvision Cursor.
- [ ] **TC-MW-12** — اختبار تشغيل NSSM ومراقبة Logs وSQLite WAL، وغياب Scheduled Task ثانية متعارضة.

### 2.4 Attendance — الوظيفة النهائية

- [ ] **TC-ATT-01** — تحويل اليوم المكتمل فقط: First In وLast Out حسب توقيت السعودية.
- [ ] **TC-ATT-02** — استخدام أحداث الموظف من الجهازين لنفس اليوم بدون إنشاء أكثر من سجل Attendance.
- [ ] **TC-ATT-03** — الـDebounce للبصمات المتقاربة، وعدم اختيار بصمة خروج وهمية.
- [ ] **TC-ATT-04** — بصمة واحدة لليوم: `FIRST_LAST_SINGLE_PUNCH` بدون إنشاء Attendance مفتوح.
- [ ] **TC-ATT-05** — عدم تغيير Attendance أُنشئ يدويًا؛ يظهر Conflict واضح للمراجعة.
- [ ] **TC-ATT-06** — إعادة تشغيل المعالجة لا تنشئ Attendance مكررًا؛ Late Punch يمكن معالجتها بأمان.
- [ ] **TC-ATT-07** — مع Mapping متأخر، تعالج Raw Events غير المرتبطة حسب سياسة الموديول بعد إضافة الربط، بدون مساس بسجلات أخرى.
- [ ] **TC-ATT-08** — تدقيق حالات `new` و`processed` و`error` وربط `attendance_id` بالحدث الصحيح.
- [ ] **TC-ATT-09** — التقارير والأذونات وشاشة حضور الموظفين تُظهر القاعدة والشركة والوقت الصحيحين.
- [ ] **TC-ATT-10** — تأكيد طريقة التعامل مع دوام اليوم السابق: إكمال وصول البيانات قبل تشغيل Daily Cron؛ تعديل التوقيت إلى ما قبل 07:00 فقط بعد اختبار واعتماد.
- [ ] **TC-ATT-11** — Bridge Cron الخاصة بالمعالجة كل 10 دقائق معطلة؛ Daily First/Last Cron مفعلة وغير معطلة بسبب `numbercall=0`.
- [ ] **TC-ATT-12** — تأكيد أن محرك Cron يُنفّذ المهام فعليًا في قواعد Test، وليس فقط `active=True`.

## 3) Production Go-Live Checklist — النسخة القابلة للتنفيذ

> لا تنفذ أي أمر تغيير على Production قبل اعتماد نتائج الاختبارات، والحصول على نسخ احتياطية وصلاحية نافذة الصيانة. يحدد مسؤول التنفيذ حالة كل خطوة مستقلة في ERP Live وRSH Live.

### 3.1 Preflight / Backups

- [ ] **LIVE-01** — اعتماد Test Cases أعلاه وتوثيق أسماء المسؤولين وتاريخ وساعة Go-Live.
- [ ] **LIVE-02** — أخذ Backup جديد لكل PostgreSQL DB متأثرة، مع Filestore، واختبار الاسترجاع إلى بيئة منعزلة.
- [ ] **LIVE-03** — أخذ Backup جديد من SQLite باستخدام Backup API أثناء الخدمة، و`integrity_check`، ونسخة من كود Middleware وملف `config.yaml` محفوظة بسرية.
- [ ] **LIVE-04** — تسجيل Commit وModule Versions وInstalled States على كل قاعدة Production؛ التأكد من Addons Paths وGit Branch المناسب وعدم التأثير على نسخة أخرى.
- [ ] **LIVE-05** — تسجيل حالة جميع Crons قبل أي تغيير: `id`، الاسم، `active`، `nextcall`، `numbercall`، `doall`، والتعامل مع المهام ذات التأثير المالي/الرسائل.
- [ ] **LIVE-06** — خطة Rollback تتضمن استعادة خدمة Windows/Config/SQLite ومسارات Odoo مع حماية أحداث أضيفت بعد آخر Backup، وعدم تشغيل نسختين ترسلان إلى نفس الوجهة بالتزامن.
- [ ] **LIVE-07** — خطة تواصل مع HR والمالية أثناء نافذة الصيانة، وتحديد Freeze ومتى تعود الخدمات.
- [ ] **LIVE-08** — حصر قواعد البيانات الأخرى على خدمة Odoo Production المشتركة وتأثير إعادة تشغيل Cron عليها (ERP/RSH/Archive وغيرها).

### 3.2 ERP Live — إجراءات وتحقق مستقلة

- [ ] **LIVE-ERP-01** — التأكد من نسخ الموديولات المثبتة وCompatibility؛ لا ترقية عمياء إذا لم تحتج.
- [ ] **LIVE-ERP-02** — تثبيت/فحص `asg_biometric.api_token` الحالي دون تغييره أو إظهاره؛ مراجعته على Middleware ERP target.
- [ ] **LIVE-ERP-03** — توثيق جهازي `zk_room_1` و`hik_room_2`، النوع، الشركة، `active=True` و`raw_only`.
- [ ] **LIVE-ERP-04** — مراجعة Mapping الموجودة (21 على ZKTeco و22 على Hikvision وقت الفحص) وأثر الموظفين غير المطابقين.
- [ ] **LIVE-ERP-05** — التأكد من `Asia/Riyadh` وتوقيت Daily Cron والـBridge Cron المعطل ومنع `Synced Attendance` من معالجة مزدوجة.
- [ ] **LIVE-ERP-06** — مراقبة سجل التسليم للـERP: الأحداث `synced` القديمة لا يعاد إرسالها، والجديدة تتحول إلى Raw Events دون Duplication.
- [ ] **LIVE-ERP-07** — معالجة الأيام المكتملة المتأخرة بناءً على مراجعة 60 `new` و104 `FIRST_LAST_SINGLE_PUNCH` وقت الفحص؛ تدوين أي استثناء HR دون توليد دخول/خروج افتراضي.
- [ ] **LIVE-ERP-08** — تدقيق Atten­dance الناتجة وحالات Raw Events بعد إصلاح الجدولة، ومطابقة عينات مع سجلات الجهازين.

### 3.3 RSH Live — إجراءات وتحقق مستقلة

- [ ] **LIVE-RSH-01** — تجهيز ورفع الموديولات بالترتيب الصحيح: `hr_attendance`، `rm_hr_attendance_sheet`، `rgb_biometric_attendance_bridge`، `rgb_biometric_first_last_attendance` بعد اعتماد Test.
- [ ] **LIVE-RSH-02** — إضافة `asg_biometric.api_token` **مستقل** عن ERP وقويّ سرًا، عبر وسيلة إعداد آمنة لا تسجل قيمته.
- [ ] **LIVE-RSH-03** — ضبط `asg_biometric_first_last.timezone=Asia/Riyadh` والتحقق من إعدادات Cron، وليس الاكتفاء بوجود المفاتيح.
- [ ] **LIVE-RSH-04** — إضافة جهازي `zk_room_1` و`hik_room_2` على RSH Live، مع الشركة الصحيحة و`raw_only`.
- [ ] **LIVE-RSH-05** — إضافة Mapping موظفي RSH الحقيقيين على كل جهاز، وفحص تكرار/غموض External IDs وإغلاق القائمة مع HR.
- [ ] **LIVE-RSH-06** — اختبار API Authentication وAllowed Employees وHeartbeat وEvent ACK على RSH Live باستخدام اختبار مضبوط غير مؤثر على الحضور.
- [ ] **LIVE-RSH-07** — تحديد تاريخ بدء RSH `start_at` وخطة Backfill المعتمدة؛ لا تسحب أو ترسل تاريخًا قديمًا غير مراجع.
- [ ] **LIVE-RSH-08** — تأكيد استقبال Raw Events لـRSH فقط، ومعالجتها إلى Attendance حسب قاعدة اليوم المكتمل، وعدم إنشاء بيانات لموظف لا يملك Mapping في RSH.

### 3.4 Middleware Windows — التحويل إلى 3.6.0

- [ ] **LIVE-MW-01** — نشر الملفات التي نجحت في E2E فقط داخل Release Package مستقل، ولا تعتمد على نقل Git working tree عشوائيًا.
- [ ] **LIVE-MW-02** — التحقق من `config.yaml` و`legacy_target_id=erp` ومن أن ERP URL لم يتغير، وتهيئة `odoo_targets` بأسرار مستقلة ومن دون تخزينها في Git.
- [ ] **LIVE-MW-03** — إعداد RSH `start_at` بموافقة HR، وعدم تشغيل RSH Target قبل صلاحية Odoo APIs والـMappings.
- [ ] **LIVE-MW-04** — التحقق من SQLite Backup جديد ومن عدم وجود Queue قيد الإرسال؛ تنفيذ Migration مرة واحدة فقط.
- [ ] **LIVE-MW-05** — إيقاف الخدمة القديمة خلال نافذة الصيانة فقط وتشغيل إصدار واحد، ثم مراقبة Logs والـCursor والـQueue لكل هدف.
- [ ] **LIVE-MW-06** — مقارنة عدد أحداث ERP قبل/بعد التحديث وعدم Replay، وفصل أرقام `pending/synced/ignored/failed` لكل هدف.
- [ ] **LIVE-MW-07** — اختبار فصل انقطاع RSH عن ERP، وقابلية استعادة RSH بدون فقد، ومنع إرسال مزدوج بين نسخ الوسيط.
- [ ] **LIVE-MW-08** — حماية Windows Service بالتشغيل التلقائي، والمنطقة الزمنية `Arab Standard Time`، والتأكد من عدم وجود Scheduled Task مزدوجة، ومراقبة مساحة Logs/SQLite.

### 3.5 Production Cron / Accounting Safety

- [ ] **LIVE-CRON-01** — اعتماد نافذة صيانة لإصلاح اختفاء Cron Thread من خدمة `odoo16-server`؛ لا Restart مفاجئ.
- [ ] **LIVE-CRON-02** — تصنيف Crons المتأخرة والمراجعة مع Accounting/Operations قبل استعادة الجدولة: Payment وEDI وProcurement وRecurring Entries وAuto Posting وEmails وHR.
- [ ] **LIVE-CRON-03** — حفظ الإعدادات الأصلية للمهام الموقوفة مؤقتًا إن لزم، وعدم تعديل `ir_cron` دون خطة واضحة.
- [ ] **LIVE-CRON-04** — بعد الإصلاح: تأكيد عودة Cron Thread وتنفيذ المهام فعليًا على ERP/RSH، ومراجعة أثرها على قواعد الإنتاج الأخرى.
- [ ] **LIVE-CRON-05** — التحقيق منفصلًا في خطأ `EDI XMLSyntaxError: PCDATA invalid Char value 24`؛ لا تعالج بإخفاء الخطأ أو تغيير بيانات فواتير دون مراجعة.
- [ ] **LIVE-CRON-06** — ضبط وقت Daily First/Last بما يحقق هدف الاستعداد قبل بداية الدوام، واختبار تشغيله على يوم مكتمل وتسجيل `nextcall` الصحيح بالتوقيت UTC.

### 3.6 قبول الإطلاق والمراقبة

- [ ] **LIVE-ACC-01** — عدد السجلات التي وصلت ERP يطابق ACK في Middleware على مستوى `event_key`، وليس مجموع العدادات فقط.
- [ ] **LIVE-ACC-02** — عدد السجلات التي وصلت RSH يطابق ACK في Middleware على مستوى `event_key`، ومرتبط فقط بموظفي RSH.
- [ ] **LIVE-ACC-03** — تحقق ممثل عن HR من مجموعة موظفين على الجهازين: First In / Last Out وغياب التكرار.
- [ ] **LIVE-ACC-04** — استثناءات Single Punch وUnmapped وManual Conflicts واضحة في التقرير وقابلة للمتابعة، دون إنشاء Attendance خاطئ.
- [ ] **LIVE-ACC-05** — عند توقف Odoo أو أحد جهازي البصمة تكون هناك Alerts / Runbook لتحديد الفجوة في السحب والتسليم والمعالجة.
- [ ] **LIVE-ACC-06** — عند الساعة المستهدفة قبل 07:00 السعودية: التحقق من معالجة **اليوم السابق المكتمل**، وتوثيق أن بداية دوام اليوم الحالي لن تملك Last Out حتى ينتهي اليوم.
- [ ] **LIVE-ACC-07** — تسليم العميل تعليمات المتابعة اليومية وحالات الخطأ والتصعيد وRollback، ثم توقيع استلام التشغيل.

## 4) سجل الاختبارات (يُحدّث تباعًا)

| Test Case | Environment | Result | Evidence | Required Live Change | Live Verified |
|---|---|---|---|---|---|
| TC-MW-UNIT-01 | Local Dev | PASS — 53 tests | `python3 -m unittest discover -s tests -q` بتاريخ 2026-10-20 | نشر إصدار 3.6.0 فقط بعد نجاح E2E | No |
| TC-CFG-01 (RSH timezone key) | RSH Test | PASS — `Asia/Riyadh` verified | SQL `ir_config_parameter` بتاريخ 2026-10-20 | تأكيد `Asia/Riyadh` على RSH Live | No |
| TC-CFG-02 (RSH API Token) | RSH Test | PARTIAL — generated by Test bootstrap; endpoint not yet verified | Odoo Shell output بتاريخ 2026-10-20 | إنشاء Token مستقل على RSH Test ثم RSH Live | No |
| TC-BOOT-RSH-01 | RSH Test | PASS — bootstrap script ran, 2 devices and token reported | Odoo Shell / Git Hash 6522374d4c بتاريخ 2026-10-20 | إعادة التهيئة المعتمدة على RSH Live بعد Test E2E فقط | No |
| TC-ENV-01 (ERP Test service) | ERP Test | BLOCKED — service not yet confirmed | فحوصات Service / dbfilter السابقة | N/A (Test prerequisite) | No |
| TC-MW-09 (SQLite backup) | Windows | PARTIAL — Backup integrity verified, restore not tried | `integrity_check=ok`، `4336` events | Backup جديد + Restore Drill قبل Migration | No |
| LIVE-CRON-01 | ERP / RSH Live | BLOCKED — thread absent | `ps -T` + 54 overdue tasks | خطة صيانة + إصلاح ومراقبة | No |

**قالب لإضافة سطر جديد:**

`TC-XX | Test DB | PASS/FAIL/BLOCKED | evidence + time | exact live configuration | No/Yes + evidence`

## 5) شروط منع الإطلاق (No-Go)

**أي حالة أدناه تمنع إعلان Go-Live كاملًا حتى تُحل ويُوثّق اختبارها:**

- API Token مفقود، Device أو Employee Mapping غير مكتمل في RSH.
- وجهة ERP Test غير معزولة، أو تم اختبار Runtime على إنتاج العميل بدل Test.
- عدم إثبات عدم فقد/تكرار الأحداث أثناء ترحيل SQLite أو إرسال الشركتين.
- عدم إثبات تشغيل Daily Cron في Odoo، أو وجود أكثر من معالج لنفس البصمات.
- عدم مراجعة أثر استعادة Crons المالية المتأخرة على قواعد الإنتاج الأخرى.
- عدم وجود Backup + Restore Plan قابل للتنفيذ للبيانات والكود والإعدادات.

## 6) الحالة التالية

**الخطوة الأولى في Test الآن:**

- قراءة قيمة Timezone الفعلية في `test_RSH` (دون أي تعديل).
- إنشاء Token آمن مستقل لـRSH Test عن طريق الإعداد الإداري المعتمد.
- إعداد Device Records وMapping على `test_RSH` ببيانات مؤكدة من HR.
- استكمال ERP Test المستقل ثم تنفيذ TC-CFG-07/08/09 لكل قاعدة.

**أول إجراء على Live لاحقًا:** تنفيذ بنود Preflight وBackups، وليس تغيير `config.yaml` أو Restart Odoo.

---
**تغيير الحالة**: أي بند يُعلّم `[x]` يجب أن يتضمن أدلة تؤكد البيئة والتاريخ والنتيجة؛ لا تعتمد على تذكر الإعدادات من المحادثة وحدها.

</div>